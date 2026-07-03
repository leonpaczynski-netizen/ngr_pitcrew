# Current Claude Handoff

## Current Objective
**Group 18A — Track Truth Library, Calibration Wizard, and Station-Based Map Matching Foundation — COMPLETE.** Full suite: **4053 pass / 6 skip / 0 fail** (45 new tests). No automated-test blockers.

**Why it exists:** the app was still treating **curvature-only detected corners** as authoritative track truth. Group 18A lays the foundation for a proper Track Truth system. Product principle: **no mapped-corner confidence ⇒ no high-confidence setup/strategy recommendation.** **Foundation only** — the Setup Brain, Strategy Brain, and Live Race Engineer are NOT yet rewired to consume it.

**New modules (pure-Python, no PyQt6):**
- `data/track_truth.py` — Track Truth data model + validation + AI guard. Enums `TrackTruthStatus` / `TrackTruthConfidence` / `TrackTruthSource` / `TrackTruthValidationIssue`; dataclasses `TrackStation`, `CornerWindow`, `CornerComplex`, `SectorMarker`, `PitLaneDefinition`, `TrackTruthManifest`, `TrackTruthModel`, `TrackTruthValidationResult`; `resolve_track_truth_model(track_id, layout_id, base_dir=None)`, `validate_track_truth_model(model)`, `can_use_track_truth_for_ai_corner_context(result)`. `track_truth_model_from_dict` returns None on schema mismatch (never raises).
- `data/track_truth_matcher.py` — station-based live map-matching foundation. `match_track_truth_position(inp, model, validation=None)` — weighted `_score_candidate` (spatial + heading + monotonic-progress + lap-wrap + max-plausible-movement + pit), a scaffold to be swapped for HMM/Viterbi later. Confidence bands mirror `track_map_matching.py` (≤5m HIGH / ≤20m MED / ≤60m LOW). Never raises.
- `data/track_truth_calibration.py` — calibration wizard. `TrackTruthWizardStage` (NOT_STARTED → CAPTURE_CENTRELINE → CAPTURE_LEFT_EDGE → CAPTURE_RIGHT_EDGE → OPTIONAL_HOT_LAP → BUILD_PROPOSED → VALIDATE → ACCEPT) + `TrackTruthCalibrationWizard`. Illegal transitions = no-ops that set `state.error`. Geometry DELEGATED to `data/track_geometry_builder.build_seed_geometry` (defensive wrapper, no duplicate algorithm); `accept()` is the only route to ACCEPT and persists via `save_seed_geometry_to_library`; `abandon()` resets, writes no file.

**UI (additive, headless-VM tests only — needs manual UAT):** `ui/track_modelling_vm.py` `format_track_truth_status()` (20-key display dict); `ui/track_modelling_ui.py` "Track Truth / Mapping" panel + `_tm_refresh_track_truth_panel()`.

**New schema:** `track_truth_model_v1` (envelope, nested `track_truth_manifest_v1`). **Runtime-built** from the existing library manifest + semantic_model — NO new JSON file in the library. Full field list in `docs/TRACK_LIBRARY_SCHEMA.md`.

**Validation gates (the spine):**
- `is_accepted` = no blockers. Blockers: non-monotonic stations, progress out of 0–100, `lap_length ≤ 0`, apex outside window, complex → missing corner, sector out of range, `corners_expected > 0` with no windows, and `NO_COORDINATE_GEOMETRY` ("Coordinate geometry unavailable — high-confidence corner mapping is blocked").
- `is_usable_for_live_mapping` = accepted AND stations present AND `manifest.corners_are_seed_verified` (default False).
- `is_usable_for_ai_corner_context` = live-mapping-usable AND `manifest.seed_geometry_available`.
- AI guard True only when accepted AND AI-context-usable; None → False. Single-member complex is a warning, not a blocker.

**Daytona status — BLOCKED (by design):** Daytona truth is built at runtime from its existing manifest + semantic model (12 corners T1–T12, sectors S1–S3, complexes BusStop=T1+T2 and Horseshoe/T10T11=T10+T11). It has no `geometry.seed_map.json`, so the model has zero stations → `NO_COORDINATE_GEOMETRY` → `is_accepted=False` → AI corner context BLOCKED. Curvature peaks are never presented as verified truth. `availability.seed_geometry` stays `false`.

**Tests:** `tests/test_group18a_track_truth.py` (26), `tests/test_group18a_track_truth_matcher.py` (9), `tests/test_group18a_track_truth_calibration.py` (10). Baseline moved 4008 → **4053** pass / 6 skip / 0 fail.

**Natural next step / deferred:** wire `TrackTruthModel` into the Setup Brain / Strategy Brain / Live Race Engineer (so recs respect the no-mapped-corner principle), and/or produce a real Daytona `geometry.seed_map.json` (acceptance stays blocked until it exists). Also deferred: full HMM/Viterbi matcher, non-Daytona tracks, automated boundary generation, deep AI prompt integration, automatic track ID. UI panel needs manual UAT.

Full detail: `docs/TRACK_INTELLIGENCE_STARTER_MODEL.md` (Group 18A), `docs/TRACK_LIBRARY_SCHEMA.md` (Track Truth Model Schema), `MASTER_TESTING_REGISTER.md` (Group 18A — Track Truth Foundation).

---

## Prior Objective (historical)
**Integration: Setup Brain + Strategy Outcome — merged to `master`.** `integration/setup-brain-strategy-overhaul` combined `feature/setup-diagnosis-engine` + `feature/strategy-outcome-comparison` (clean, no conflicts) and was **merged to `master`** (merge commit `7254835`, pushed). **Full combined suite: 3984 pass / 6 skip / 0 fail.** Merged after automated tests passed; **runtime UAT still pending** (SETUP_BUILDER_UAT.md + STRATEGY_BUILDER_UAT.md) — run it against `master` and log results.

Delivered (see MASTER_TESTING_REGISTER.md "Integration — Setup Brain + Strategy Outcome"):
- **Setup Brain:** deterministic app-side diagnosis before the AI call (`strategy/setup_diagnosis.py`), driver tuning-model + hard-constraints at the top of every setup prompt, post-AI engineering validation with regenerate-once-then-surface, low-confidence track-model guard, structured liked/hated setup-history learning. Bug fixes: springs in **Hz** (was N/mm); timed race renders "N minutes, Timed Race" (was "1 laps, Lap Race"). Proven on the Porsche RSR '17 / Fuji regression: ride-height blocked, aero prioritised, gearbox preserved. Tests: `tests/test_group38_setup_diagnosis.py` (74).
- **Strategy Outcome:** deterministic total-race-time comparison (`strategy/outcome.py`) — head-to-head ranking, delta-vs-fastest, confidence, refuel-rate-based pit time, and previously-hidden risk fields on the cards; "pit loss" → "pit time". Tests: `tests/test_group39_strategy_outcome.py` (53) + `tests/test_group40_strategy_card_rendering.py` (44).

**Deferred (carried forward):** setup history key omits track layout (config_id re-hash risk); from-scratch "Build Setup with AI" lacks the post-AI validation loop (no telemetry at build time); strategy finishing-position prediction needs rival telemetry.

**Remaining step:** runtime UAT (against `master`) not yet executed. No automated-test blockers.

---

## Prior Objective (historical)
Group 31 complete. Race-Engineer Prompt Directives, Validation, and Bottoming Classifier. 3426 pass / 6 skip / 0 fail. 144 tests in `tests/test_group31_race_engineer.py`. Both entry points (`build_setup_advice_response` and `build_combined_setup_response`) now normalise, validate, and strip locked fields from the AI response before returning. The UI renders validation errors as a banner. Defects C1/C2/C3/I1/I5 resolved.

## Group 31 — Session Notes (2026-06-29)

**Problem solved:** The setup advisor's AI responses had no server-side validation, could recommend locked fields, allowed no-ops to pass through, used a 1200-token response cap, and had no race-engineer discipline in the prompt.

**What was added / fixed:**

- **`telemetry/recorder.py`:** `LapStats.bottoming_positions: list` field added; `_compute_stats` captures rising-edge XYZ on bottoming events (mirrors snap_throttle_positions pattern).

- **`strategy/driving_advisor.py`:**
  - `_normalise_changes`: no-op stripping — when `from == to_clamped` the change is dropped before it reaches the AI context or the Apply button.
  - `_derive_locked_fields(allowed_tuning) -> set[str]`: maps allowed-tuning category strings to canonical setup param names; has inline comments explaining `steering` and `nitrous` have no canonical params yet.
  - `_validate_setup_response(parsed, car_name, allowed_tuning, locked_fields, setup) -> dict`: 7 checks (unresolvable field, out-of-range, locked, no-op, string-not-number, >4 changes warning, setup_fields mismatch); appends `validation_errors` list; never drops changes.
  - `_classify_bottoming_location(positions, loc_id, lay_id) -> str`: delegates to `enrich_telemetry_issues`; votes on `matched_segment_type`; returns a category string or "unknown".
  - `_race_engineer_directives(...)`: generates AC1–AC13 directive block for injection into both prompts; includes I1 fix — when `setup` is passed and ride height is at the per-car max AND bottoming > 0, emits explicit "do NOT recommend raising it" with field names; when below max, emits "IS permissible".
  - `_get_previous_ai_context(feature, prior_outcomes=None)`: renders structured block with do-not-repeat instruction when `prior_outcomes` is a non-empty list.
  - `build_setup_advice_response`: max_tokens 1000→1500; post-call normalise+validate+C3a locked-strip.
  - `build_combined_setup_response`: max_tokens 1200→1500 (C2); C1 setup_fields rebuild after normalise; C3a locked-field strip from both `changes` and `setup_fields`; normalise+validate; passes `prior_outcomes`.
  - `_build_setup_prompt` and `_build_combined_prompt`: inject `_race_engineer_directives` block + extended JSON schema (AC8 keys: `primary_issue`, `issue_classification`, `validation_targets`, `do_not_change_reasoning`, `confidence`, `expected_validation`).

- **`ui/setup_builder_ui.py`:**
  - `_format_validation_errors_banner(validation_errors: list) -> str`: pure module-level helper — returns HTML orange-banner string; returns "" for empty list.
  - `_display_setup_result`: reads `validation_errors` from parsed JSON; calls `_format_validation_errors_banner`; injects banner before the changes list.

**Defects resolved in this session:**
- C1/I3: `build_combined_setup_response` now rebuilds `setup_fields` from surviving normalised changes — stale no-op keys never reach the validator or Apply button.
- C2: `build_combined_setup_response` max_tokens corrected to 1500.
- C3a: Locked-field changes stripped from both `changes` and `setup_fields` after validation in both entry points.
- C3b: `validation_errors` rendered as orange warning banner in `_display_setup_result`.
- I1/AC3: `_race_engineer_directives` explicitly names ride-height fields at their per-car max and states they must not be raised.
- I5: `_derive_locked_fields` has inline comments for unmapped categories.

**Files added / modified:**
- `telemetry/recorder.py`: `bottoming_positions` field + population logic
- `strategy/driving_advisor.py`: all changes listed above
- `ui/setup_builder_ui.py`: `_format_validation_errors_banner` helper + `_display_setup_result` banner injection
- `tests/test_group31_race_engineer.py` (NEW): 144 tests covering AC1–AC14 + defect-fix targeted tests

**Full suite result after Group 31: 3426 pass / 6 skip / 0 fail**

---

## Group 17U — Session Notes (2026-06-26)

**Problem solved:** After Group 17T, track seed/coordinate files were discovered ad hoc from the flat `data/track_seed_maps/` directory with no schema versioning, no per-layout metadata, no semantic model separation, and no availability summary. As the track library grows, this becomes unmanageable. Group 17U replaces ad hoc file discovery with a structured, versioned track-library registry.

**What was added / fixed:**

- **New `data/track_library.py` module:** Dataclass hierarchy — `TrackLibraryIndex`, `TrackMetadata`, `TrackLibraryAvailability`, `TrackLayoutManifest`, `TrackSemanticModel`, `ValidationAcceptance`, `ValidationWarningThresholds`, `ValidationRules`, `SourceManifest`, `TrackLibraryAuditResult`. All load functions accept optional `base_dir` for testability. `resolve_seed_coordinate_map(track_id, layout_id)` returns `(SeedCoordinateMap|None, source_label)` with library-first, legacy-fallback, then none resolution. `audit_track_library_layout()` returns full availability picture.

- **New `data/track_library/` directory structure:** JSON-based (not YAML) for consistency with seed map files. `index.json` → track index. Per-track `track.json` with layout list. Per-layout directory named `<layout_id>/` containing `manifest.json`, `semantic_model.json`, `validation_rules.json`, `source_manifest.json`, `geometry.seed_map.json` (when available), `accepted_models/`, `calibration_runs/`.

- **Daytona Road Course library skeleton:** All files present except `geometry.seed_map.json`. `manifest.json` sets `availability.seed_geometry = false`. 12 corners T1–T12, 3 sectors S1–S3, 2 complexes (BusStop=T1+T2, T10T11=T10+T11). Source manifest documents T1 apex at 8.2% as verified from UAT telemetry; all other corner windows estimated.

- **`SeedAuditResult` extended:** New fields `seed_source` (`"track_library"/"legacy_fallback"/"none"`), `library_manifest_loaded` (bool), `validation_rules_loaded` (bool). All default to safe values so existing callers see no change.

- **`audit_layout_seed()` updated:** Calls `audit_track_library_layout()` and `resolve_seed_coordinate_map()` when track/layout IDs given. Falls back to legacy-only path if `data.track_library` import fails. Missing centreline message now references the library path.

- **`format_alignment_summary()` updated:** `"seed_source"` key added to the returned dict with display-friendly values ("Track library", "Legacy fallback", "Unavailable", "—").

- **`ui/dashboard.py` updated:** "Seed source" panel row added before "Seed truth source". `_tm_refresh_alignment_panel()` uses `resolve_seed_coordinate_map()` from `data.track_library` (library-first).

**Daytona acceptance status:** BLOCKED. No geometry file. `audit_layout_seed()` returns `seed_source="none"`, `has_seed_centreline=False`. Full geometry match cannot be verified. To unblock: place coordinate data in `data/track_library/tracks/daytona_international_speedway/layouts/daytona_international_speedway__road_course/geometry.seed_map.json` and set `availability.seed_geometry = true` in `manifest.json`.

**New test file:** `tests/test_group17u_track_library_schema.py` — 83 tests covering all 13 categories.

**Files added / modified:**
- `data/track_library.py` (NEW): Full dataclass hierarchy + resolver/loader/audit functions
- `data/track_library/index.json` (NEW): Track library index, schema `track_library_index_v1`
- `data/track_library/tracks/daytona_international_speedway/track.json` (NEW): Track metadata
- `data/track_library/tracks/.../layouts/daytona_international_speedway__road_course/manifest.json` (NEW)
- `data/track_library/tracks/.../layouts/.../semantic_model.json` (NEW): 12 corners, 3 sectors, 2 complexes
- `data/track_library/tracks/.../layouts/.../validation_rules.json` (NEW): acceptance + warning thresholds
- `data/track_library/tracks/.../layouts/.../source_manifest.json` (NEW): data provenance
- `data/track_intelligence.py`: `SeedAuditResult` extended; `audit_layout_seed()` library-first
- `ui/track_model_alignment_vm.py`: `format_alignment_summary()` returns `"seed_source"` key
- `ui/dashboard.py`: "Seed source" row; `_tm_refresh_alignment_panel()` uses library resolver
- `tests/test_group17u_track_library_schema.py` (NEW): 83 tests
- `docs/TRACK_LIBRARY_SCHEMA.md` (NEW): Full schema reference

**Schema versions introduced in 17U:**
- `track_library_index_v1`, `track_metadata_v1`, `track_layout_manifest_v1`
- `track_semantic_model_v1`, `validation_rules_v1`, `source_manifest_v1`

**Next step to create Daytona seed geometry:**
1. Run accepted calibration laps in GT7 and export telemetry x/y per station.
2. Create `geometry.seed_map.json` using `export_seed_coordinate_map_json()` from `data/track_seed_coordinate_map.py`.
3. Place file in `data/track_library/tracks/daytona_international_speedway/layouts/daytona_international_speedway__road_course/geometry.seed_map.json`.
4. Set `"seed_geometry": true` in `manifest.json` availability.

## Group 17T — Session Notes (2026-06-26)

**Problem solved:** After Group 17S, runtime UAT showed the modelled lap (5393 m) vs seed (5729 m) delta was correctly blocked, but the app had no way to explain WHY the map was short or verify coordinate geometry. Accept was blocked correctly, but the user had no coordinate-level evidence.

**What was added / fixed:**

- **DEF-17T-001 (Seed centreline/coordinate map unavailable blocks true matching):**
  New `data/track_seed_coordinate_map.py` — `SeedMapStation`, `SeedCoordinateMap` dataclasses, `find_seed_coordinate_map_path()`, `load_seed_coordinate_map()`, `export_seed_coordinate_map_json()`, `import_seed_coordinate_map_json()`, `resample_seed_map()`. File convention: `data/track_seed_maps/<track_id>__<layout_id>.seed_map.json`. `audit_layout_seed()` updated to accept `track_location_id` and `layout_id_str` and check for seed coordinate map file, setting `has_seed_centreline` and `centreline_point_count` accordingly.

- **DEF-17T-002 (Compare seed map vs modelled telemetry map):**
  New `data/track_map_geometry_alignment.py` — `MapMismatchRange`, `CornerCoordinateMatch`, `SectorCoordinateMatch`, `CoordinateTransform`, `TrackMapGeometryAlignmentResult` dataclasses. `align_maps_geometry(station_map, seed_map, seed_layout)` main entry point. Falls back to length-only when seed map absent. Reports `has_coordinate_comparison`, `mean_coord_error_m`, `max_coord_error_m`, `missing_section_ranges`, `corner_matches`, `sector_matches`, `coordinate_transform`, `blockers`, `warnings`.

- **DEF-17T-003 (Detect and explain missing track sections):**
  `_detect_missing_sections()` in `track_map_geometry_alignment.py`: when coordinates exist, scans for large inter-station jumps (> 10× expected step). Fallback: assumes missing section is at lap boundary (estimated start %–100%). Blocker text includes "Rebuild from complete clean laps crossing S/F line."

- **DEF-17T-004 (Stop using 200-point reference path for serious alignment):**
  `align_maps_geometry()` reads `station_map.stations` directly (full-resolution, 1 m spacing). `model_stations_count` in result reports the full count. Result is independent of any 200-pt reference path.

- **DEF-17T-005 (Handle coordinate transform between seed map and GT7 telemetry map):**
  `estimate_coordinate_transform()`: centroid alignment → translation; RMS-radius ratio → scale; rotation scan (15° coarse + 1° fine) minimising mean nearest-neighbour error; returns `CoordinateTransform` with `quality` 0–1. `_apply_transform()` applies translation + rotation + scale. Scale mismatch > 5% → warning.

- **DEF-17T-006 (Corner and sector matching use coordinate/progress truth):**
  `_match_corners()` uses seed map `has_corner_markers` station `corner_id` fields, matched to model corners by progress proximity (± 3% threshold). `_match_sectors()` reads `has_sector_markers` station `sector_id` fields. Progress-window fallback (Group 17S) remains active when no seed coordinate map.

- **DEF-17T-007 (UI overlay must show seed vs modelled map):**
  `TrackMapDrawData.seed_centreline: List[MapPoint]` added (defaulted field). `build_track_map_draw_data()` accepts optional `seed_coordinate_map` parameter and populates `seed_centreline` from `SeedCoordinateMap.stations` using `(x, y)` coordinates. `project_to_screen()` projects `seed_centreline`. `seed_overlay_note` cleared when seed map is present.

- **DEF-17T-008 (Recalibration must guide user toward fixing full-lap mismatch):**
  `_tm_rebuild_model()` dialog updated: now lists 4 explicit steps including "Start Calibration mode before leaving pits", "Drive 2–3 full clean laps crossing S/F line", "Avoid pit-lane entries and lap-start offsets", and a note about checking correct layout selection.

**New schema (Group 17T):**
- `SeedMapStation`: station_m, progress_pct, x, y, z, width_left_m, width_right_m, corner_id, sector_id
- `SeedCoordinateMap`: track_location_id, layout_id, source, confidence, lap_length_m, start_finish_station_m, stations, has_z_coordinates, has_corner_markers, has_sector_markers, has_width_corridor, notes
- `MapMismatchRange`, `CornerCoordinateMatch`, `SectorCoordinateMatch`, `CoordinateTransform`, `TrackMapGeometryAlignmentResult`
- File convention: `data/track_seed_maps/<track_id>__<layout_id>.seed_map.json`, schema: `seed_coordinate_map_v1`

**Daytona status:** No seed coordinate map file exists yet. Daytona full geometry match remains blocked. To enable: create `data/track_seed_maps/daytona_international_speedway__daytona_international_speedway__road_course.seed_map.json` with GT7 coordinate data from accepted telemetry runs.

**New test file:** `tests/test_group17t_seed_coordinate_map.py` — 55 tests covering all 8 defects.

**Files modified:**
- `data/track_seed_coordinate_map.py` (NEW): SeedCoordinateMap model, file I/O, resample
- `data/track_map_geometry_alignment.py` (NEW): geometry alignment engine, transform estimator
- `data/track_seed_maps/` (NEW directory): empty, awaiting seed map files
- `data/track_intelligence.py`: `audit_layout_seed()` now accepts track/layout IDs, checks for seed coordinate map file, sets `has_seed_centreline` + `centreline_point_count`
- `ui/track_map_vm.py`: `TrackMapDrawData.seed_centreline` field (defaulted); `build_track_map_draw_data()` accepts `seed_coordinate_map`; `project_to_screen()` projects seed_centreline
- `ui/track_model_alignment_vm.py`: `format_geometry_alignment_summary()`; `format_alignment_summary()` accepts `geo_result` + returns `"geometry_match"` key
- `ui/dashboard.py`: "Geometry match" alignment panel row; `_tm_refresh_alignment_panel()` computes geometry result via `align_maps_geometry()`; recalibration dialog with 4-step guidance
- `tests/test_group17t_seed_coordinate_map.py`: 55 new tests

## Group 17S — Session Notes (2026-06-26)

**Problem solved:** Six runtime defects observed after Group 17R UAT. The Daytona seed had no corner windows, sectors, or complex definitions — the alignment system was operating entirely on curvature peaks and integer counts. Turn assignment was wrong (Straight 0–7.3% assigned T2). Lap delta 5.1% was only a warning, not a blocker.

**What was added / fixed:**

- **DEF-17S-001 (Daytona seed lacks corner window truth):**
  Added 12 corner definitions (T1–T12) to Daytona Road Course in `track_modelling_seed.yaml`. All source: "estimated", confidence: "low". T1 apex at 8.2% confirmed from UAT telemetry. Other windows approximated from track layout knowledge.

- **DEF-17S-002 (Corner complexes not represented):**
  Added `CornerComplexDefinition` dataclass to `data/track_intelligence.py`. Added `corner_complexes` field to `TrackLayoutSeed`. Daytona has 2 complexes: BusStop (T1+T2) and T10T11 (T10+T11, coaching name "Horseshoe"). `_parse_complex_def()` parses from YAML.

- **DEF-17S-003 (Lap delta 5.1% must be a blocker):**
  In `data/track_model_alignment.py`, the `delta_pct > _MAX_LAP_DELTA_GOOD_PCT` branch is now a BLOCKER (not a warning). Daytona's 5.1% delta will now appear in the Blockers row with an explicit explanation of possible causes.

- **DEF-17S-004 (Turn assignment uses curvature rank, not seed windows):**
  `_tm_refresh_seg_table()` in `ui/dashboard.py` now resolves `SeedCornerDefinition` list for the selected layout. Segment midpoint is checked against each corner window: if it falls inside a window, that corner_id is assigned. A segment at 3.65% (pre-T1 straight) receives no assignment. A segment at 8.2% correctly receives T1. Falls back to nearest-station-map-corner proximity only when no seed windows are present.

- **DEF-17S-005 (Legacy warnings still leak after station map loads):**
  New `_tm_refresh_seg_diagnostics_labels()` method in `dashboard.py`. Called at end of `_tm_try_load_station_map_from_disk()` and `_tm_try_build_station_map()`. Re-filters "Corner count mismatch" and "corners vs expected" warnings and updates `_tm_lbl_seg_status`. The existing inline filter in `_tm_detect_segments_safe()` is still there as the first filter pass.

- **DEF-17S-006 (No seed audit diagnostics):**
  Added `SeedAuditResult` dataclass and `audit_layout_seed()` function to `data/track_intelligence.py`. Added `format_seed_audit_summary()` to `ui/track_model_alignment_vm.py`. `format_alignment_summary()` now accepts optional `layout_seed` and includes `"seed_audit"` key. New "Seed data available" row in alignment panel shows: lap length, N sectors, N corner windows, N complexes, centreline status.

- **New schema fields:**
  - `SeedSectorDefinition` dataclass (sector_id, display_name, start/end_progress_pct, source, confidence)
  - `CornerComplexDefinition` dataclass (complex_id, display_name, member_corner_ids, start/end_progress_pct, sector_id, coaching_name, notes, source, confidence)
  - `SeedAuditResult` dataclass (all availability flags + counts + max_match_status)
  - `TrackLayoutSeed.sector_definitions: list[SeedSectorDefinition]`
  - `TrackLayoutSeed.corner_complexes: list[CornerComplexDefinition]`

**New test file:** `tests/test_group17s_seed_definition_authoring.py` — 36 tests covering all defects.

**Files modified:**
- `data/track_intelligence.py`: 3 new dataclasses, 2 new parse helpers, audit_layout_seed(), updated _parse_layout(), updated TrackLayoutSeed
- `docs/track_modelling_seed/track_modelling_seed.yaml`: Daytona Road Course enriched with corners:, sector_definitions:, corner_complexes:
- `data/track_model_alignment.py`: lap delta > 5% is now a blocker, not a warning
- `ui/track_model_alignment_vm.py`: format_seed_audit_summary(), format_alignment_summary() has optional layout_seed param + seed_audit key
- `ui/dashboard.py`: "Seed data available" alignment row, _tm_refresh_alignment_panel() passes layout_seed, seed-window-based turn assignment in _tm_refresh_seg_table(), _tm_refresh_seg_diagnostics_labels() method
- `tests/test_group17s_seed_definition_authoring.py`: 36 new tests

## Group 17R — Session Notes (2026-06-26)

**Problem solved:** Six runtime defects observed during Daytona Road Course UAT after Group 17Q.

**What was added / fixed:**

- **DEF-17R-001 (Corner labels are curvature peaks, not verified positions):**
  `format_alignment_summary()` in `ui/track_model_alignment_vm.py` now returns explicit `seed_position_status` text: *"Unavailable — corner labels are curvature peaks, not verified positions"* when `seed_corner_positions_available=False`. Makes clear that T1-T12 labels in the current Daytona model are unverified curvature rankings, not positionally matched to the real Daytona corners.

- **DEF-17R-002 (No seed overlay note in TrackMapDrawData):**
  `build_track_map_draw_data()` in `ui/track_map_vm.py` now sets `seed_overlay_note` from `station_map.seed_corner_positions_available`. When unavailable: *"Seed centreline not available — showing telemetry-derived model only. Corner labels are curvature peaks, not verified seed positions."*. `project_to_screen()` passes the note through to the projected result.

- **DEF-17R-003 (Seed map source not explicit):**
  New `"seed_truth_source"` key in `format_alignment_summary()` and new "Seed truth source" row in the alignment panel. Shows either *"Metadata only — no coordinate or window data"* or *"Seed corner windows (N defs)"* depending on whether corner definitions are present in the seed YAML.

- **DEF-17R-004 (Old detection warnings leaking):**
  In `dashboard._tm_detect_segments_safe()`, "Corner count mismatch" and "corners vs expected" warnings from `detect_track_segments()` are now suppressed when a station map with seeded corners is authoritative. The old telemetry-based corner count is irrelevant when the station map owns the corner geometry.

- **DEF-17R-005 (Rebuild/Recalibrate button was a no-op):**
  `_tm_rebuild_model()` now: clears `self._tm_station_map = None`, clears `self._tm_alignment_result = None`, pushes empty draw data to both map widgets, resets the alignment panel to "Not built", and shows a dialog: *"Station map cleared. Start Calibration and drive clean laps to rebuild the track model."*. Updated button tooltip to explain what it does.

- **DEF-17R-006 (Lap offset not explained):**
  The `_off_note` QLabel in the Lap Offset Calibration group now explains: what lap offset calibration does, and what the three status states mean (Not loaded / Zero offset provisional / Calibrated).

**New test file:** `tests/test_group17r_seed_overlay_alignment.py` — 38 tests covering DEF-17R-001 through DEF-17R-006.

**Files modified:**
- `ui/track_model_alignment_vm.py`: `format_alignment_summary()` — new `seed_truth_source` key, updated `seed_position_status` text
- `ui/track_map_vm.py`: `build_track_map_draw_data()` — sets `seed_overlay_note`; `project_to_screen()` — passes note through
- `ui/dashboard.py`: new alignment panel row, `_tm_refresh_alignment_panel()` wiring, `_tm_rebuild_model()` fix, warning suppression in `_tm_detect_segments_safe()`, tooltip and lap offset note updates
- `tests/test_group17r_seed_overlay_alignment.py`: 38 new tests

## Group 17Q — Session Notes (2026-06-26)

**Problem solved:** Group 17P only capped corners at corners_expected=12. It chose the top-12 strongest curvature peaks without verifying they were at the correct Daytona T1–T12 positions. Accept Track Model could reach ACCEPTABLE_MATCH based on count alone.

**What was added:**
- `data/seed_corner_matching.py` (NEW): `CornerMatchStatus` enum, `CornerCandidateMatch` dataclass, `match_peaks_to_seed_windows()` greedy algorithm.
- `data/track_intelligence.py`: `SeedCornerDefinition` dataclass (per-corner progress window: corner_id, apex_progress_pct, start/end_progress_pct, direction, sector_id, source, confidence). `TrackLayoutSeed.corner_definitions` list field (empty by default — backward compatible). `_parse_corner_def()` + YAML `corners:` key support.
- `data/track_station_map.py`: `TrackStationMap.seed_corner_positions_available` bool field. `build_track_station_map()` branches: if `corner_definitions` present → calls `_find_curvature_peaks()` + `match_peaks_to_seed_windows()` to select official corners by window; else → existing top-N cap. JSON I/O updated.
- `data/track_model_alignment.py`: Four new fields on `TrackModelAlignmentResult`: `seed_corner_positions_available`, `corner_position_match`, `corners_matched`, `corner_candidate_matches`. `align_track_model()` now: (a) if seed has no corner defs → warns, marks all as SEED_POSITION_UNAVAILABLE, caps match status at GOOD_MATCH; (b) if seed has defs → checks each official corner against its expected window, computes PASS/PARTIAL/FAIL. ACCEPTABLE_MATCH only reachable when `corner_defs` present + no blockers + lap delta < 2%.
- `ui/track_model_alignment_vm.py`: `format_alignment_summary()` returns 4 new keys: `seed_position_status`, `corners_matched`, `corner_position_match`, `corner_position_color`.
- `ui/dashboard.py`: 3 new label rows in alignment panel (Seed corner positions, Corners matched, Corner pos match). Wired in `_tm_refresh_alignment_panel()`.
- `tests/test_group17q_seed_corner_matching.py`: 29 tests, all passing.

**Key acceptance rule change:** ACCEPTABLE_MATCH (and therefore Accept Track Model button enabled) now REQUIRES `corner_defs` in the layout seed. Without seed corner position data, the system is honest: max status = GOOD_MATCH, Accept disabled, UI says "Unavailable — count only".

## Source of Truth
- docs/PROJECT_STATE.md
- docs/MASTER_TESTING_REGISTER.md
- docs/AI_ENGINEERING_VALIDATION_REPORT.md, only when the scoped task requires it

## Architecture Boundaries
- Event Planner owns race/event settings.
- Garage owns cars.
- Setup Builder consumes Event + Car.
- Strategy Builder consumes Event + Car + Practice Data.
- History owns session loading.
- Live Race Engineer consumes Event + Strategy + Telemetry.

## Do Not Touch
- No unrelated refactors.
- No duplicate race/event/session state.
- No duplicate strategy fuel sources.
- No fake telemetry assumptions.
- No silent fallback logic that hides broken data flow.
- No broad UI rewrites unless explicitly scoped.

## Required Validation
- Update or add tests where practical.
- Update docs/MASTER_TESTING_REGISTER.md.
- Provide manual UAT steps.
- Confirm no unrelated behaviour changed.

## End Of Session Notes

### Session: Group 17P — Seed-to-Telemetry Track Model Alignment (2026-06-25)

**Root cause fixed (DEF-17P-UAT-001/005):** `_detect_corners()` in `data/track_station_map.py` kept ALL curvature peaks above threshold without capping at `corners_expected`. Daytona with 36 curvature peaks and `corners_expected=12` would create T1-T36 as official corners. Fixed by: when `detected > corners_expected`, take the top N by curvature magnitude; excess peaks stored as `extra_curvature_peaks` with XP1..XPn IDs (never official turns).

**New modules:**
- `data/track_model_alignment.py` — `TrackModelAlignmentResult`, `align_track_model()`, accepted model JSON persistence
- `ui/track_model_alignment_vm.py` — `format_alignment_summary()`, `get_acceptance_button_states()`, `format_mismatch_reasons()`

**`data/track_station_map.py` changes:**
- `_detect_corners()` returns `(official, extras)` tuple; caps to `corners_expected` when detected > expected
- `TrackStationMap` gains `extra_curvature_peaks: List[SeededCorner]` field
- JSON export/import updated to include `extra_curvature_peaks`

**`ui/track_map_vm.py` changes:**
- `TrackMapDrawData` gains `seed_overlay_note: str` (shown when seed centreline unavailable)

**`ui/dashboard.py` changes:**
- Segment Review renamed → Segment Diagnostics; 6 per-segment manual-approval buttons hidden (attrs preserved to avoid AttributeError in legacy handler methods)
- Review Approval panel replaced → Track Model Alignment panel with alignment metrics, Accept Track Model button (green, disabled until ACCEPTABLE_MATCH), Rebuild/Recalibrate button
- New methods: `_tm_run_alignment()`, `_tm_refresh_alignment_panel()`, `_tm_accept_track_model()`, `_tm_rebuild_model()`, `_tm_try_load_accepted_model()`
- `_tm_on_layout_changed()`: now calls `_tm_try_load_accepted_model()` in addition to station map load
- `_tm_try_build_station_map()`: calls `_tm_run_alignment()` after every successful build
- `_tm_try_load_station_map_from_disk()`: calls `_tm_run_alignment()` after loading

**New imports in `ui/dashboard.py`:**
- `data.track_model_alignment`: `align_track_model`, `export_accepted_model_json`, `find_accepted_model_path`, `import_accepted_model_json`
- `ui.track_model_alignment_vm`: `format_alignment_summary`, `get_acceptance_button_states`, `format_mismatch_reasons`

**New test file:** `tests/test_group17p_alignment.py` — 34 tests covering all 6 DEFs

**Test result: 2088 pass / 5 skip / 0 fail** (+34 vs Group 17O Round 2)

---

### Session: Group 17O UAT Remediation Round 2 — DEF-17O-UAT-004 through 008 (2026-06-25)

**Root cause fixed (CRITICAL):** `_tm_try_build_station_map()` at line 2770 iterated `self._tm_seed_result.layouts` — `TrackSeedLoadResult` has `.track_locations` not `.layouts`. This AttributeError was silently caught, causing the station map never to build, the track map never to display, and Daytona to show only 5 curvature-detected corners instead of the seeded 12.

**`ui/dashboard.py` changes:**
- `_tm_try_build_station_map()`: replaced broken `for layout in self._tm_seed_result.layouts:` with `get_selected_layout(self._tm_seed_result, loc_id, lay_id)` (already imported); also reads `loc_id` from location combo (was missing); after build, calls `_export_station_map()` to persist JSON; updates `_tm_lbl_build_info` to show `"Path: N pts | Conf: X | Map: N stations / N corners"`
- `_tm_on_layout_changed()`: calls `_tm_try_load_station_map_from_disk(loc_id, lay_id)` — new method that loads saved station map JSON when layout is selected, populating both map widgets immediately
- `_tm_refresh_seg_table()`: matches each segment's `lap_progress_mid` to nearest `SeededCorner` (< 15% threshold) to populate Turn column for non-apex segments
- `_TELEMETRY_OVERLAY_SEG_TYPES`: added `BRAKING_ZONE` and `TRACTION_ZONE` — both tagged with Porsche RSR car-specific warnings, not universal track geometry
- New imports: `export_station_map_json`, `import_station_map_json`, `find_station_map_path` from `data.track_station_map`

**`tests/test_group17o_uat_defects.py` changes:**
- 40 tests total (was 23); added `TestDef17OUAT004StationMapCountDisplay` (3), `TestDef17OUAT005SeedLookupFix` (5), `TestDef17OUAT007MapDisplayFix` (2), `TestDef17OUAT008StationMapPersistence` (6)
- Updated `TestDef17OUAT002OverlayFiltering`: added `test_braking_and_traction_zones_are_overlay`; updated `test_geometry_types_not_in_overlay_set` (removed BRAKING/TRACTION from geometry list); updated `test_review_segment_filtering_preserves_geometry` (uses APEX_ZONE as geometry proxy)

**Test result: 2054 pass / 5 skip / 0 fail**

---

### Session: Group 17M — Runtime UAT and Calibration Workflow Hardening (2026-06-24)

**New module:** `data/track_modelling_runtime_check.py` (pure Python, no PyQt6)

**New doc:** `docs/TRACK_MODELLING_RUNTIME_UAT.md` — 15-section manual UAT checklist

**`ui/track_modelling_vm.py` additions (all pure Python, testable without QApplication):**
- `_WORKFLOW_ERROR_MESSAGES` — 11-key error string dict
- `get_workflow_error_message(error_key)` — safe lookup with unknown-key fallback
- `get_calibration_button_states(ctrl_state, has_track, has_completed_laps, has_ref_path, has_review_model, selected_segment_id=None, has_track_length=False)` → 15-key bool dict
- `format_calibration_status_extended(status_summary, last_packet_age_s=None)` → 7-key dict
- `format_lap_offset_status(offset_calibration=None, track_length_m=None)` → 7-key dict
- `format_live_resolver_status_summary(loc_id, lay_id, ...)` → newline-separated string

**`data/track_modelling_runtime_check.py`:**
- `RuntimeCheckResult` — 14-field dataclass with `summary_text()` → compact display string
- `run_track_modelling_runtime_check()` — never raises; duck-typed; aggregates resolver/offset/live_position/live_segment

**`data/lap_distance_mapper.py` change:**
- `create_offset_zero()` default `source` changed from `"manual"` to `"zero_offset"` to match spec; `ValueError` raised on non-positive `track_length_m`

**`ui/dashboard.py` additions:**
- `_tm_lbl_packet_age` label with green/amber/red colour feedback
- `_tm_last_packet_time: Optional[float]` and `_tm_offset_calibration` instance vars
- Lap Offset Calibration QGroupBox with Create Zero Offset / Load Offset / Save Offset buttons and status/detail/warning labels
- `_tm_get_track_length_m()`, `_tm_update_packet_age_label()`, `_tm_update_offset_status()`
- `_tm_create_zero_offset()`, `_tm_load_offset()`, `_tm_save_offset()` handlers
- `_tm_update_cal_buttons()` extended for offset buttons (create_zero = needs track+length; load = needs track; save = needs offset)
- Signal connections in `_connect_signals()` for the three new offset buttons

**Button state rules implemented:**
- `create_zero_offset`: has_track AND has_track_length
- `load_offset`: has_track
- `save_offset`: has_offset_calibration

**Provisional vs validated offset:**
- Provisional: source == "zero_offset" OR confidence in (low, unknown)
- Validated: confidence in (high, medium) AND source != "zero_offset"

**Files changed:**
- `data/track_modelling_runtime_check.py` — new file
- `ui/track_modelling_vm.py` — 5 new functions appended after `get_review_button_states()`
- `data/lap_distance_mapper.py` — `create_offset_zero()` updated
- `ui/dashboard.py` — packet age label, offset group, new methods, signal connections
- `tests/test_group17m_runtime_hardening.py` — 94 new tests (all pass)
- `docs/TRACK_MODELLING_RUNTIME_UAT.md` — new file
- `docs/PROJECT_STATE.md` — build stats updated; Group 17M row added
- `MASTER_TESTING_REGISTER.md` — Group 17M section added
- `docs/TRACK_INTELLIGENCE_STARTER_MODEL.md` — Group 17M section added
- `docs/CURRENT_CLAUDE_HANDOFF.md` — this file updated

**Tests run:**
- `tests/test_group17m_runtime_hardening.py`: 94/94 pass
- Full suite: 1815 pass / 5 skip / 0 fail (1820 collected)

---

### Session: Group 17M UAT Defect Remediation (2026-06-25)

**Defects fixed:**

**DEF-17M-UAT-001 — Lap Count Mismatch Display**
- Root cause: `lap_count = len(session.laps)` counts ALL closed segments; quality data only available after Build
- Fix: `format_lap_count_info(status_summary) -> dict` added to `track_modelling_vm.py` — returns `captured_text`, `quality_text`, `explanation`; `_tm_update_cal_status()` uses it; tooltip shows explanation when gap exists

**DEF-17M-UAT-002 — Detect Segments Crash**
- Root cause: `seed_result.layouts` (line 2607) — `TrackSeedLoadResult` has no `.layouts` attribute; `AttributeError` in Qt slot crashes app
- Fix: `_tm_detect_segments()` split into outer try/except catcher + `_tm_detect_segments_safe()` inner; crash shows QMessageBox.critical; `seed_result.layouts` replaced with `get_selected_layout(seed_result, loc_id, lay_id)`

**DEF-17M-UAT-003 — Saved File Not Discoverable After Restart**
- Root cause: `ctrl._saved_path` is None after restart (new controller); UI never audited disk
- Fix: `audit_track_model_files(loc_id, lay_id, search_dir=None) -> TrackModelFileAudit` added to `track_calibration.py`; `_tm_on_layout_changed()` calls `_tm_audit_and_show_saved_files()`; `TrackModelFileAudit` dataclass + `reference_path_filename()` + `format_file_audit_status()` vm helper

**Files changed (UAT remediation):**
- `data/track_calibration.py` — `reference_path_filename()`, `TrackModelFileAudit` dataclass, `audit_track_model_files()` appended
- `ui/track_modelling_vm.py` — `format_lap_count_info()`, `format_file_audit_status()` appended
- `ui/dashboard.py` — new imports, `_tm_update_cal_status()` updated, `_tm_detect_segments()` refactored + `_tm_detect_segments_safe()` added, `_tm_on_layout_changed()` updated, `_tm_audit_and_show_saved_files()` added
- `tests/test_group17m_uat_defects.py` — new file, 49 tests (all pass)
- `docs/TRACK_MODELLING_RUNTIME_UAT.md` — UAT Defect Register section appended
- `docs/PROJECT_STATE.md` — build stats + Group 17M UAT row added
- `MASTER_TESTING_REGISTER.md` — Group 17M UAT Remediation section added

**Tests run:**
- `tests/test_group17m_uat_defects.py`: 49/49 pass
- Full suite: 1864 pass / 5 skip / 0 fail (1869 collected)

---

### Session: Group 17N UAT Defect Remediation (2026-06-25)

**Defect fixed:**

**DEF-17N-UAT-004 — Detect Segments Requires Live Session Despite Saved Reference Path**
- Root cause: `detect_track_segments()` needs raw `CalibrationLap.samples` (per-sample TelemetrySample arrays). `save_reference_path()` only saved the 200-point aggregated ReferencePath JSON — raw lap data was discarded on every restart.
- Fix: Three-layer change:
  1. **`data/track_calibration.py`** — Added `calibration_laps_filename()`, `export_calibration_laps_json()` (USABLE laps + all TelemetrySample fields serialised), `import_calibration_laps_json()` (reconstructs CalibrationSession from disk). Extended `TrackModelFileAudit` with `calibration_laps_exists`, `calibration_laps_usable_count`, `can_detect_segments` property (True when both files present and loadable), `is_legacy_ref_path_only` property (True when ref path exists but no laps file). `audit_track_model_files()` now checks for laps file. `summary_line()` includes laps count.
  2. **`data/track_calibration_runtime.py`** — `save_reference_path()` now writes BOTH files per save: `<loc>__<lay>.reference_path.json` and `<loc>__<lay>.calibration_laps.json`. Laps write is best-effort (ref path save succeeds independently).
  3. **`ui/dashboard.py`** — `_tm_detect_segments_safe()` rewritten with three-path logic: (A) active session with usable laps → run immediately; (B) laps file found on disk → load via `import_calibration_laps_json()`, reconstruct CalibrationSession, run detection; (C) legacy ref path only → informational dialog explaining pre-17N format and what to do. `_tm_audit_and_show_saved_files()` updated: Detect Segments enabled when `ctrl_has_ref OR disk_can_detect OR disk_legacy`; save-path label includes laps count.
  4. **`ui/track_modelling_vm.py`** — `format_file_audit_status()` updated: `detail_text` includes `"{N} laps persisted"` when laps file present, or `"no lap data saved"` for legacy. `load_status` distinguishes "Detect Segments ready — lap data available from disk" vs "Pre-17N format — re-run calibration once".

**Files changed:**
- `data/track_calibration.py` — calibration_laps_filename, export/import_calibration_laps_json, TrackModelFileAudit extensions, audit + summary_line updated
- `data/track_calibration_runtime.py` — save_reference_path() writes both files
- `ui/dashboard.py` — _tm_detect_segments_safe() three-path logic, _tm_audit_and_show_saved_files() laps-aware
- `ui/track_modelling_vm.py` — format_file_audit_status() laps-aware
- `tests/test_group17m_uat_defects.py` — test_file_found_load_ok_saved_text updated; test_file_found_legacy_no_laps_shows_preformat_message added
- `tests/test_group17n_uat_defects.py` — new file, 41 tests (all pass)
- `docs/TRACK_MODELLING_RUNTIME_UAT.md` — DEF-17N-UAT-004 appended to defect register
- `docs/PROJECT_STATE.md` — build stats + Group 17N UAT row added
- `MASTER_TESTING_REGISTER.md` — Group 17N UAT Remediation section added, header updated

**Saved file format:** `<loc>__<lay>.calibration_laps.json` alongside `<loc>__<lay>.reference_path.json`
**Legacy path:** is_legacy_ref_path_only=True → informational dialog; user must run one new calibration session and re-save.

**Tests run:**
- `tests/test_group17n_uat_defects.py`: 41/41 pass
- Full suite: 1906 pass / 5 skip / 0 fail (1911 collected)

---

### Session: Group 17N UAT-005 Defect Remediation (2026-06-25)

**Defect fixed:**

**DEF-17N-UAT-005 — No Usable Calibration Laps Message Lacks Actionable Diagnostics**
- Root cause 1: `CalibrationLap.quality` defaults to `REJECTED` and `build_reference_path()` never wrote quality assessment results back to the lap objects. `detect_track_segments()` filtered by `quality == USABLE` → found none → generic error even after a successful Build.
- Root cause 2: `_tm_build_path()` only showed `result.errors`, discarding per-lap rejection reasons in `result.warnings`.
- Fix:
  1. **`data/track_calibration.py`** — `build_reference_path()` now mutates `CalibrationLap.quality` and `quality_reasons` immediately after `assess_session_laps()` runs (both success and failure paths). Added `diagnose_calibration_session(session) -> dict` — structured diagnostic snapshot with `total_laps`, `usable/rejected/low_confidence_count`, `total_samples`, `per_lap` list, `all_reasons`, `most_common_reason`, `car_id`, `has_any_laps`. Never raises.
  2. **`data/track_segment_detection.py`** — Added `assess_session_laps` to import. Added `_build_no_usable_laps_errors(session) -> list[str]` helper that re-assesses quality and returns per-lap diagnostic lines + context-specific recommended action. `detect_track_segments()` calls this instead of the hardcoded "record more laps with the Porsche 911 RSR".
  3. **`ui/track_modelling_vm.py`** — Added `format_build_failure_diagnostics(result, session=None) -> str` — multi-line dialog string with primary error, lap quality counts (usable/rejected/low-conf), per-lap reasons from `result.warnings`, car ID, and a context-specific recommended action (too-few-samples → UDP advice; zero-xyz → on-track advice; off-track → 30% limit explanation; outlier → consistent laps advice). Added `_min_samples()` helper.
  4. **`ui/dashboard.py`** — Added `format_build_failure_diagnostics as _format_build_diag` to import. `_tm_build_path()` now calls `_format_build_diag(result, session)` instead of generic `"\n".join(result.errors)`.

**Files changed:**
- `data/track_calibration.py` — quality mutation in build_reference_path, diagnose_calibration_session added
- `data/track_segment_detection.py` — assess_session_laps import, _build_no_usable_laps_errors helper
- `ui/track_modelling_vm.py` — format_build_failure_diagnostics, _min_samples added
- `ui/dashboard.py` — _format_build_diag import, _tm_build_path updated
- `tests/test_group17n_uat_defects.py` — test_daytona_ref_path_is_legacy_until_resaved updated for three-way state
- `tests/test_group17n_uat005_defects.py` — new file, 32 tests (all pass)
- `docs/TRACK_MODELLING_RUNTIME_UAT.md` — DEF-17N-UAT-005 appended
- `docs/PROJECT_STATE.md` — build stats + Group 17N UAT-005 row added
- `MASTER_TESTING_REGISTER.md` — Group 17N UAT-005 section added, header updated

**Post-fix behavior:**
- Build success: all session laps now have `quality = USABLE`; Detect Segments immediately works on active session.
- Build failure: dialog shows "Lap 1 rejected: Too few telemetry samples (10 < 50)" style detail plus recommended action.
- Detect with no usable laps: error includes lap counts, per-lap rejection reasons, car ID, and action (e.g., "Confirm GT7 Custom UDP Output is enabled").

**Tests run:**
- `tests/test_group17n_uat005_defects.py`: 32/32 pass
- Full suite: 1938 pass / 5 skip / 0 fail (1943 collected)

---

### Session: Group 17O — Seeded 1m Track Map, Width Corridor, Map Matching, and Visual Verification (2026-06-25)

**Root cause of old segment weirdness:** Group 17E segment detection used telemetry behaviour (speed minima, brake, throttle, gear, RPM) to detect track anatomy. This produced non-geometry items (limiter approaches, kerb candidates, gear zones, fuel-saving candidates) instead of true corner boundaries.

**New three-layer architecture:**
- Layer 1 — Track Model: stable circuit truth from X/Y/Z geometry only. No brake/gear/throttle.
- Layer 2 — Driver Reference Path: car-specific driving line (existing ReferencePath)
- Layer 3 — Telemetry Overlay: behaviour events attached to known stations (NOT geometry)

**New files:**

`data/track_station_map.py`:
- `StationPoint` — one station (station_m, progress_pct, x, y, z, heading_rad, curvature, gradient, widths, corner_id, corner_phase, confidence)
- `SeededCorner` — T1..Tn from seed + placeholder filling
- `TrackStationMap` — container with `station_count()`, `get_station_at()`
- `resample_path_to_uniform_spacing(xyz_points, spacing_m=1.0)` — arc-length resampling
- `build_track_station_map(ref_path, layout_seed, spacing_m=1.0)` — main builder
- Corner detection: `_find_curvature_peaks()` iterative peak suppression + placeholder filling for `corners_expected` guarantee
- `export_station_map_json()` / `import_station_map_json()` — JSON I/O (schema `track_station_map_v1`)

`data/track_map_matching.py`:
- `MapMatchConfidence` — HIGH (≤5m), MEDIUM (≤20m), LOW (≤60m), UNKNOWN (>60m)
- `MapMatchResult` — station_m, progress_pct, lateral_offset_m, edge distances, confidence, is_pit_likely
- `find_nearest_station_idx()`, `match_position_to_map()`, `is_likely_outlap()`, `map_match_samples()`
- Pit detection: speed < 8 kph OR dist > 60m from centreline → `is_pit_likely=True`

`data/track_width_model.py`:
- `WidthObservation`, `WidthEstimate` dataclasses
- `collect_lateral_offsets()`, `build_width_estimates()`, `apply_width_estimates_to_map()`
- `is_near_left_edge()`, `is_near_right_edge()`, `unused_track_width_pct()`

`ui/track_map_vm.py` (pure Python, NO PyQt6):
- `MapPoint`, `CornerLabel`, `CarDot`, `TrackMapDrawData` dataclasses
- `build_track_map_draw_data(station_map, match_result, telemetry_trace)` — world-space primitives
- `project_to_screen(draw_data, canvas_w, canvas_h, margin)` — pixel projection with Y-flip

**Dashboard changes (`ui/dashboard.py`):**
- `TrackMapWidget(QWidget)` — new QPainter-based canvas class before MainWindow
- Track Modelling tab: "Station Map" QGroupBox with `TrackMapWidget` (min height 300px) added after Calibration Session group
- Live tab: logo replaced with `self._live_map_widget = TrackMapWidget()` in mid_row
- `_tm_try_build_station_map()` — builds station map from ref path after successful Build Reference Path, updates both map widgets
- `_tm_update_live_map_dot(packet)` — called from `_tm_on_calibration_packet()`, matches packet XYZ to station map and refreshes both widgets
- New state: `self._tm_station_map = None` (Group 17O)

**Tests:** `tests/test_group17o_track_station_map.py` — 76 tests across 14 categories (all pass):
1. Creating 1m station model from reference data
2. Resampling path to 1m stations
3. Mapping X/Y/Z to nearest station
4. Calculating station_m and progress_pct
5. Calculating lateral_offset_m
6. Calculating left/right edge distance
7. Handling missing/unknown width safely
8. Ignoring pit/out-lap fragments
9. Keeping seeded 12-corner Daytona structure
10. Separating telemetry overlays from track geometry
11. Producing drawing primitives without PyQt
12. Producing live car-dot from mapped telemetry
13. Low-confidence map matching state
14. Legacy low-resolution (200-point) reference path handling

**Files changed:**
- `data/track_station_map.py` — new file
- `data/track_map_matching.py` — new file
- `data/track_width_model.py` — new file
- `ui/track_map_vm.py` — new file
- `ui/dashboard.py` — TrackMapWidget class, map widget on both tabs, _tm_try_build_station_map, _tm_update_live_map_dot, new imports
- `tests/test_group17o_track_station_map.py` — new file, 76 tests

**Tests run:**
- `tests/test_group17o_track_station_map.py`: 76/76 pass
- Full suite: 2014 pass / 5 skip / 0 fail (2019 collected)

---

### Session: Group 17L — Lap-Start Offset Calibration and Road-Distance Mapping (2026-06-24)

**New module:** `data/lap_distance_mapper.py` (pure Python, no PyQt6)

**Enums:** `LapDistanceMappingStatus` (6 values: mapped / mapped_with_wrap / no_distance_data / no_track_length / invalid_offset / error), `LapDistanceMappingConfidence` (high / medium / low / unknown)

**Dataclasses:** `LapStartOffsetCalibration` (stores offset between GT7 road_distance and model distance_along_lap_m; JSON-persistable to `data/track_models/<loc>__<lay>__lap_offset.json`), `LapDistanceMappingResult` (full error-status return from any mapping call), `LapDistanceMapperConfig` (min_track_length_m=100, clamp_progress=True)

**Core conversion formula:** `model_distance = (road_distance - offset_m) % track_length_m`
  - `offset_m = normalise_distance(gt7_start_distance_m - model_start_distance_m, track_length_m)`
  - `normalise_distance` uses Python modulo (handles negatives safely)
  - Wrap-around detection: `raw < 0 or raw >= track_length_m` → status = MAPPED_WITH_WRAP + warning

**Functions:** `normalise_distance()`, `calculate_lap_start_offset()`, `map_road_distance_to_lap_distance()`, `map_road_distance_to_lap_progress()`, `create_offset_zero()`, `create_offset_from_reference_path()`, `export_offset_calibration_json()`, `import_offset_calibration_json()`, `load_offset_calibration_for_track()`

**`data/live_segment_resolver.py` updates:**
- `LivePosition.road_distance_m: Optional[float] = None` — raw GT7 field (populated, not converted)
- `packet_to_live_position()` — populates `road_distance_m` from `packet.road_distance`; `distance_along_lap_m` still NOT set (requires calibration)
- `enrich_position_with_road_distance(position, offset_calibration) -> LivePosition` — standalone helper; returns new instance with `distance_along_lap_m` set; no-op on missing data
- `resolve_live_segment(…, offset_calibration=None)` — new Priority 3: road_distance_m + calibration → distance_along_lap_m; confidence downgraded when calibration is LOW/UNKNOWN

**Matching priority (updated):** segment_id → lap_progress → road_distance+offset → distance_along_lap_m → XYZ nearest → nearest midpoint → unresolved

**Explicitly deferred:** track auto-detection, PTT marker capture, voice announcements, lap progress from weak evidence only, seed-only as trusted coaching truth, Porsche calibration as universal truth, live engineer rewrite

**69 tests, all passing.** Full suite: 1721 pass / 5 skip / 0 fail.

---

### Session: Group 17K — Segment-Aware Live Coaching Rules (2026-06-24)

**New module:** `data/live_segment_coaching.py` (pure Python, no PyQt6)

**Enums:** `LiveCoachingCueType` (13 incl. no_call), `LiveCoachingPriority` (low/medium/high/urgent), `LiveCoachingSuppressionReason` (12 values)

**Dataclasses:** `LiveCoachingCue` (cue_type, priority, text, basis fields, repetition count, lap/progress context), `LiveCoachingDecision` (suppressed, cue, suppression_reason, all_candidates, debug_info), `LiveCoachingConfig` (9 tuneable fields; fuel-save and tyre-management cues opt-in disabled by default)

**Core function:** `build_live_coaching_decision(live_segment_result, enriched_issues, current_sample, config, previous_cues, current_lap, current_progress) -> LiveCoachingDecision`

**Gate sequence:** seed_only → rejected_segment → needs_more_laps → low_confidence → no issues → build candidates (filter by segment_id/type, count repetitions, apply rules) → sort by priority → cooldown → max_cues_per_lap → return cue

**25-entry cue template table:** covers brake_lock / wheelspin / oversteer / understeer / poor_exit_drive / wrong_gear / limiter_hit / fuel_saving_opportunity / tyre_wear_hotspot × relevant segment types with exact+fallback matching

**Helpers:** `format_live_coaching_for_prompt()` (returns "" when suppressed, block with basis when cue fires); `get_live_coaching_debug_metadata()` (4 debug fields); `_format_cue_text()` (inserts or gracefully removes {segment} placeholder without inventing names); `_downgrade_priority()`, `_cooldown_suppressed()`, `_confidence_is_usable()`

**`DrivingAdvisor` wiring:** `_get_live_coaching_context(live_position, laps) -> str`; injected into coaching prompt `extra_sections` after `live_segment_block`

**78 tests, 19 test classes** in `tests/test_group17k_live_segment_coaching.py`

**Deferred:** TTS/voice delivery, track auto-detection, multi-cue display, tyre management cues (noisy), fuel-save cues (require strategy context)

---

### Session: Group 17J — Live Current Segment Resolver (2026-06-24)

**New module:** `data/live_segment_resolver.py` (pure Python, no PyQt6)

**Enums:** `LiveSegmentResolutionConfidence` (HIGH/MEDIUM/LOW/UNKNOWN), `LiveSegmentResolutionStatus` (matched/matched_nearest/no_reviewed_model/no_position_data/no_segment_bounds/error)

**Dataclasses:** `LivePosition`, `LiveSegmentMatch`, `LiveSegmentResolverResult`, `LiveSegmentResolverConfig`

**Core function:** `resolve_live_segment(loc_id, lay_id, position, base_dir, config)` — never raises; matching priority: segment_id exact → lap_progress range → distance_along_lap_m via ref path → XYZ nearest via ref path → nearest midpoint → unresolved

**GT7 limitations (documented, not worked around):**
- No native lap_progress in packet — `packet_to_live_position()` never populates it
- `road_distance` is absolute (not lap-relative) — not used as `distance_along_lap_m`
- XYZ→reference path→lap_progress is the primary position path

**Adapters:** `packet_to_live_position(packet)` (duck-typed, guards paused/loading/off-track/zero-xyz, never raises); `format_live_segment_for_engineer(result)` (compact text, no invented names); `get_live_segment_context_for_prompt()` (AI block, "" for no_reviewed_model)

**`strategy/driving_advisor.py` changes:**
- `_get_live_segment_context(live_position=None) -> str` — new method; returns "" when no position or no IDs; never raises
- `_build_coaching_prompt()`, `_build_setup_prompt()`, `_build_combined_prompt()` — each gets optional `live_position=None` parameter; live_segment_block injected into `extra_sections` after track_intel_block

**Test file:** `tests/test_group17j_live_segment_resolver.py` — 78 tests, 17 test classes

**Full suite: 1574 pass / 5 skip / 0 fail**

**Deferred (documented in TRACK_INTELLIGENCE_STARTER_MODEL.md):**
- Lap-start distance offset calibration (for road_distance → distance_along_lap_m conversion)
- Voice position announcements using live resolver
- Track auto-detection from telemetry

---

### Session: Group 17H — Track Intelligence AI Prompt Integration (2026-06-24)

**New module:** `strategy/track_context_prompt.py` (pure Python, no PyQt6, no state)

**Public function:** `get_track_context_for_ai(track_location_id, layout_id) -> str`
- Missing/empty IDs: returns compact `"Track Intelligence unavailable: no selected track/layout was provided."` warning; never raises
- Present: delegates to `build_resolved_track_context_for_prompt()` from `data.track_model_resolver` (lazy import inside try block)
- Resolver exception: returns safe error note with exception class and message; never raises or propagates

**`strategy/ai_planner.py` changes:**
- `RaceParams.track_location_id: str = ""` and `RaceParams.layout_id: str = ""` — new optional dataclass fields
- `_build_race_prompt(track_context="")` — track context section injected before `## Practice lap times`
- `_build_practice_prompt(track_context="")` — same injection point
- `_build_setup_from_scratch_prompt(track_context="")` — section injected after race conditions block
- `build_car_setup(track_location_id="", layout_id="")` — calls `get_track_context_for_ai()`; passes to prompt builder; adds `track_context_included`, `track_location_id`, `layout_id` to `structured_payload`
- `analyse_strategy()` — resolves context from `params.track_location_id/layout_id`; payload updated; "Track Intelligence unavailable" added to `_warnings` when IDs missing
- `analyse_practice_session()` — same

**`strategy/driving_advisor.py` changes:**
- `DrivingAdvisor._get_track_intelligence_context()` — new method; reads `config["strategy"]["track_location_id"/"layout_id"]`; calls `get_track_context_for_ai()`; never raises
- `_build_coaching_prompt()` — `track_intel_block` prepended to `extra_sections`
- `_build_setup_prompt()` — same
- `_build_combined_prompt()` — same
- `_build_feeling_prompt()` — intentionally NOT updated (car-specific, not track-specific)

**`ui/dashboard.py` changes:**
- `_tm_on_layout_changed()` — stores `loc_id`/`lay_id` to `config["strategy"]["track_location_id"/"layout_id"]` when Track Modelling layout selected
- `_run_ai_analysis()` — passes `track_location_id`/`layout_id` from config into `RaceParams` dict
- `_run_practice_analysis()` — same; debug print updated with track context presence info
- `_run_build_setup()` — reads IDs from config; passes to `build_car_setup()`

**Source of truth for track/layout IDs:**
- Set when user selects location/layout in Track Modelling tab (NOT from event planner or telemetry)
- Stored in `config["strategy"]["track_location_id"]` / `["layout_id"]`
- If not set → all AI prompts receive "Track Intelligence unavailable" warning section

**Tests:** 56 new tests in `tests/test_group17h_track_context_prompt.py` — 16 test classes. Full suite: **1420/1425 green** (5 skipped unchanged).

**Key design decisions:**
- Thin helper module: zero state, zero PyQt6, zero direct model file parsing
- Resolver is the single boundary — `get_track_context_for_ai` never touches track model files directly
- Missing IDs → warning in every prompt (not a crash, not silent omission)
- Seed-only/not-AI-ready/missing each return their own distinct warning block (from resolver, unchanged)
- Porsche boundary note carried through from resolver on all contexts

**Deferred:**
- Live current-segment lookup
- Telemetry-to-segment issue enrichment
- Wiring `layout_id` from Event Planner (currently only Track Modelling tab selection)
- `_build_feeling_prompt` track context injection
- Track auto-detection from telemetry

**Recommended next task:** Group 17J — live current-segment lookup (which segment is the car currently in during practice/qualifying).

---

### Session: Group 17I — Telemetry Issue to Segment Enrichment (2026-06-24)

**New module:** `data/track_issue_enrichment.py` (pure Python, no PyQt6)

**Enums:** `TrackIssueType` (10 values), `TrackIssuePhase` (7 values), `TrackIssueEnrichmentConfidence` (4 values)

**Dataclasses:** `RawTelemetryIssue`, `EnrichedTelemetryIssue`, `TrackIssueEnrichmentResult`

**Core enrichment:** `enrich_telemetry_issues(raw_issues, loc_id, lay_id, base_dir) -> TrackIssueEnrichmentResult`
- Resolves reviewed track model via `resolve_best_track_model()`
- Loads reference path (`<loc>__<layout>.reference_path.json`) for XYZ→lap_progress conversion
- Matching priority: segment_id exact → lap_progress range → distance_along_lap_m → XYZ nearest → nearest midpoint → unresolved
- Never raises; all exceptions captured as result.warnings

**Confidence rules:**
- Engineer_validated/AI_ready model → HIGH base; reviewed → MEDIUM; seed_only → LOW; missing → UNRESOLVED
- REJECTED segment → UNRESOLVED; NEEDS_MORE_LAPS → LOW; UNREVIEWED → capped MEDIUM
- `nearest` match method → base confidence downgraded one level

**Implication mapping:** Deterministic dict keyed `(issue_type, segment_type)` covering:
- brake_lock+braking_zone → brake_bias, LSD braking, front damping; driver: brake release, trail braking
- wheelspin+corner_exit/traction → LSD accel, rear damping, rear ARB; driver: throttle pickup, short shift
- limiter_hit+straight/gear_zone → top gear ratio, final drive; driver: upshift timing
- poor_exit_drive+corner_exit → LSD accel, exit gear, rear grip; driver: apex speed, throttle timing
- oversteer+exit/apex → rear ARB soften, rear toe, rear downforce; driver: earlier throttle
- understeer+entry/apex → front springs/ARB, front downforce; driver: corner entry speed

**Adapters:**
- `issues_from_lap_stats(laps) -> list[RawTelemetryIssue]` — from lock_up/wheelspin/oversteer/snap_throttle/over_braking position lists
- `issues_from_corner_issues(corner_issues) -> list[RawTelemetryIssue]` — decodes `CornerIssue.corner_id` ("P500_-200") to approximate XYZ

**Prompt helper:** `summarise_enriched_issues_for_prompt(enriched_issues) -> str`
- Groups by (segment_display_name, issue_type)
- Lists unique lap numbers; limits to 8 per group with "… (N total)"
- Unresolved section: never invents corner names; includes "do not invent corner names" instruction

**`strategy/driving_advisor.py` changes:**
- `_get_enriched_issue_context(laps) -> str` — new method; reads track/layout IDs from config; calls enrichment pipeline; returns summary or ""; never raises
- `_build_coaching_prompt()`, `_build_setup_prompt()`, `_build_combined_prompt()` — include `enriched_issues_block or corner_issues_summary` in extra_sections (enriched takes precedence when non-empty)

**`strategy/ai_planner.py`:** No code changes needed — `corner_issues_summary` parameter already flows through all prompt builders.

**Tests:** 76 new tests in `tests/test_group17i_track_issue_enrichment.py` — 15 test classes. Full suite: **1496/1501 green** (5 skipped unchanged).

**Key design decisions:**
- Never invent corner names for unresolved issues
- Enriched block takes precedence over legacy `corner_issues_summary` when non-empty
- XYZ → lap_progress via reference path (not raw distance); falls back gracefully when path missing
- All matching is silent — no exceptions propagate to callers

**Deferred:**
- Live current-segment lookup
- Track auto-detection from telemetry
- PTT marker capture
- Graphical split/merge segment editing

---

### Session: Group 17G — Approved Track Model Resolver and Modelling Status Promotion (2026-06-24)

**New module:** `data/track_model_resolver.py` (pure Python, no PyQt6)

**Enums:** `TrackModelSourceType` (6), `TrackModelResolutionStatus` (6) — both `str, Enum`

**Dataclasses:** `ResolvedTrackModel` (full model snapshot with counts/blockers/warnings), `TrackModelResolverResult` (resolution outcome with all_candidate_paths + errors)

**Core resolver:** `resolve_best_track_model(loc, layout, base_dir)` — maturity priority: engineer_validated > ai_ready > reviewed > seed_only > missing; ties resolved by created_at (newest wins); malformed files silently skipped

**Prompt context builder:** `build_resolved_track_context_for_prompt(loc, layout, base_dir)` — not yet wired to AI prompts; includes seed warning / reviewed segments / Porsche boundary note / blockers

**Schema extension (`data/track_segment_review.py`):**
- `TrackModelReviewResult.modelling_status: Optional[str] = None` (backward-compatible)
- `export_review_json()` computes and writes `modelling_status` (engineer_grade / user_reviewed / segment_detected)
- `import_review_json()` reads it; old files get `None`

**`ui/track_modelling_vm.py`:** `format_resolver_summary(resolver_result)` → 8-key dict for UI display

**`ui/dashboard.py`:**
- Import: `resolve_best_track_model as _resolve_track_model`, `format_resolver_summary as _format_resolver_summary`
- `_tm_resolver_result` instance var
- "Resolver Status" QGroupBox: 5 labels + blockers + warnings; updates on layout select + after save
- `_tm_refresh_resolver()` method — resolves model, formats, updates labels

**Tests:** 68 new tests in `tests/test_group17g_track_model_resolver.py` — 13 test classes. Full suite: **1364/1369 green** (5 skipped unchanged).

**Key design decisions:**
- Seed YAML is never mutated — modelling_status is persisted in reviewed JSON only
- Seed-only fallback always shows warnings — no silent downgrade to unqualified seed data
- Porsche boundary note always in prompt context (braking/gear/traction not universal truth)
- `build_resolved_track_context_for_prompt` is ready for wiring; NOT yet integrated into any AI caller

**Deferred:**
- Wiring prompt context into Setup Builder / Strategy Builder / Practice Analysis / Live Race Engineer (Group 17H)
- Graphical split/merge editing
- Track auto-detection from telemetry

**Recommended next task:** Group 17H — wire `build_resolved_track_context_for_prompt()` into AI prompt builders (`driving_advisor.py`, `ai_planner.py`); promote modelling status display in Practice Review and Setup Builder context labels.

---

### Session: Group 17F — Segment Review and Track Model Approval (2026-06-24)

**New module:** `data/track_segment_review.py` (pure Python, no PyQt6)

**Enums:** `SegmentReviewStatus` (8 values), `SegmentReviewAction` (7 values)

**Dataclasses:** `ReviewedTrackSegment` (original detection fields + review state; `display_name` property; `is_reviewed` property), `TrackModelReviewResult` (detection metadata + segment list)

**Action functions (7):** `confirm_segment`, `rename_segment` (blank ignored), `reject_segment`, `mark_needs_more_laps`, `mark_split_required`, `mark_merge_required`, `promote_engineer_validated` (CONFIRMED only)

**Aggregate helpers:** `review_completion_pct(review) → float`, `is_ai_ready(review) → (bool, list[str])` with 5-blocker rule set

**JSON I/O:** schema `track_model_review_result_v1`; filename `<loc>__<layout>__reviewed_segments__<session_id>.json` in `data/track_models/`

**`ui/track_modelling_vm.py` additions:** `format_segment_row`, `format_review_summary`, `get_review_button_states`

**`ui/dashboard.py` changes:**
- Import: 9 functions from `track_segment_review` + 3 vm helpers
- `_tm_detect_segments()` auto-creates review and populates table on detection success
- "Segment Review" QGroupBox: 8-col read-only QTableWidget, 6 action buttons, "Save Reviewed Model" button
- "Review Approval" QGroupBox: 7 stat labels (detected/reviewed/confirmed/rejected/needs-laps/completion%/ai-ready/blockers)
- 11 new methods + 8 new signal connections

**Tests:** 122 new tests in `tests/test_group17f_segment_review.py` — 14 test classes. Full suite: **1296/1301 green** (5 skipped unchanged).

**Deferred:**
- Graphical split/merge editing (currently flags only)
- Reviewed segment integration into AI prompts (Group 17G+)
- `modelling_status` promotion after review save

**Recommended next task:** Group 17G — integrate reviewed segments into `build_seed_track_context_for_prompt()` and/or promote `modelling_status` to `segment_detected` after saving a reviewed model.

---

### Session: Group 17E — Automatic Track Segment Detection (2026-06-24)

**New module:** `data/track_segment_detection.py` (pure Python, no PyQt6)

**Enums:** `TrackSegmentType` (12 values), `TrackSegmentDirection`, `TrackSegmentDetectionConfidence`

**Dataclasses:** `SegmentDetectionConfig`, `DetectedTrackSegment`, `SegmentDetectionResult`

**Detection:**
- `detect_segments_from_lap(lap, config, ...)` — single-lap: speed minima → apex candidates; walk back/forward for braking + exit; emits `braking_zone`, `corner_entry`, `apex_zone`, `corner_exit`, `traction_zone` per corner; fills gaps with `straight` / `fuel_saving_candidate`
- `detect_track_segments(session, reference_path, layout_seed, config)` — multi-lap: clusters apex candidates by lap_progress across laps; confirmed corners from ≥ 2 laps; auxiliary: gear zones, limiter zones, kerb candidates, fuel-save candidates
- `assign_corner_numbers(segments, expected_corner_count)` — assigns T1/T2… by progress; mismatch warning; never invents corners
- `export_segment_detection_json()` / `import_segment_detection_json()` — schema `segment_detection_result_v1`

**Key design choices:**
- No steering angle (not in GT7) → heading from XZ position delta; direction = `UNKNOWN` when no movement
- Car-specific segments (braking/traction/limiter/gear/fuel-save) tagged with `calibration_car_id`; track-geometry (apex/straight/kerb) not tagged
- `layout_seed.corners_expected` → warning only; detection count never inflated
- Rejected laps excluded before detection

**`ui/dashboard.py` changes:**
- Import `detect_track_segments as _detect_track_segments`
- "Detect Segments" button (enabled when `ctrl.can_save`)
- 3 new status labels: `_tm_lbl_seg_summary`, `_tm_lbl_seg_expected`, `_tm_lbl_seg_status`
- `_tm_detect_segments()` method + `_connect_signals()` wiring

**Tests:** 99 new tests in `tests/test_group17e_track_segment_detection.py` — 22 test classes. All 1174 pass.

**Recommended next task:** Group 17F — wire `build_seed_track_context_for_prompt()` into AI practice/coaching prompts; or Group 17G — promote `modelling_status` to `reference_path_built` / `segment_detected` after successful calibration steps.

---

### Session: Group 16 — Phase 2 Per-Lap Telemetry (2026-06-23)

#### Phase 2-D: Schema Migration v3 + TelemetryFrame/LapStats tyre temps
- `telemetry/recorder.py` — `TelemetryFrame` gains `tyre_temp_fl/fr/rl/rr: float = 0.0`; `LapStats` gains `tyre_temp_fl/fr/rl/rr_avg: float = 0.0`; `_compute_stats()` averages per-corner temps from frames (skips 0.0 frames); `record_frame()` injects tyre temps from packet
- `data/session_db.py` — DDL adds 4 `tyre_temp_*_avg REAL NOT NULL DEFAULT 0.0` cols to `lap_records`; `_V3_ALTER_COLUMNS`, `_migrate_v3()`, PRAGMA user_version=3; `write_lap()` persists all 4 via `getattr(stats, ...)` fallback

#### Phase 2-A/B/C: DB query methods + AI prompt wiring
- `data/session_db.py` — `get_session_laps()` gains `exclude_pit`, `exclude_out`, `limit` params + expanded SELECT including 9 telemetry columns; `get_recent_fuel_sequence(car_id, track, limit=15)` returns chronological fuel consumption (pit/out/zero excluded); `get_compound_lap_sequences(car_id, track, session_id=0, limit_per_compound=25)` returns per-compound lap-time sequences
- `strategy/ai_planner.py` — `_build_per_lap_telemetry_block()` formats per-lap table (Phase 2-A); `_build_fuel_trend_block()` formats avg/std-dev/95th-pct with `[measured]` tag (Phase 2-B); `_build_compound_sequence_block()` formats per-compound sequences with linear-regression deg rate (Phase 2-C); `analyse_practice_session()` + `_build_practice_prompt()` gain `per_lap_telemetry: list | None = None`; `analyse_strategy()` + `_build_race_prompt()` gain `fuel_sequence` + `compound_sequences`
- `ui/dashboard.py` — `_run_practice_analysis()` captures `_hist_session_id` before thread; worker calls `get_session_laps(_hist_session_id, exclude_pit=True, exclude_out=True, limit=5)` in try/except; passes `per_lap_telemetry=_per_lap_telem`; `_run_ai_analysis()` queries fuel_sequence + compound_sequences before thread; passes both to `analyse_strategy()`

#### Tests
- `tests/test_group16_per_lap_telemetry.py` — 74 new tests (all pass)
- `MASTER_TESTING_REGISTER.md` — Group 16 section added
- `docs/PROJECT_STATE.md` — Group 16 row added; build stats updated (643/648 pass)

### Tests Run
- `tests/test_group16_per_lap_telemetry.py`: 74/74 pass
- Full suite: 643 pass / 5 skip / 0 fail (648 collected)

---

### Session: Group 15A — DEF-P3-013 Fix (2026-06-23)

### Files Changed
- `strategy/_ai_client.py` — `AILogEntry` gains `car_id: int = 0` and `track: str = ""` fields; `call_api()` gains matching kwargs; all three `AILogEntry` construction sites (debug/success/exception) pass them through
- `strategy/ai_planner.py` — `analyse_strategy()`, `analyse_practice_session()`, `build_car_setup()` gain `car_id: int = 0`; thread to `call_api()` with `track=params.track` or `track=track`
- `strategy/driving_advisor.py` — all four `call_api()` sites (`build_coaching_response`, `build_setup_advice_response`, `build_combined_setup_response`, `build_driver_feeling_response`) pass `car_id=self._car_id_ref[0], track=_track_da`
- `ui/dashboard.py` — `_run_ai_analysis()` resolves `_car_id_strat` before worker; `_run_practice_analysis()` passes `car_id=_car_id_hist`; `_run_build_setup()` resolves `_car_id_build` before worker; `_on_ai_log_entry_dict()` passes `car_id`/`track` when reconstructing AILogEntry from DB rows
- `tests/test_group15a_ai_log_car_track.py` — 56 new tests (all pass)
- `MASTER_TESTING_REGISTER.md` — DEF-P3-013 closed; AWR-063/068 closed; Group 15A section added
- `docs/PROJECT_STATE.md` — Group 15A row added; build stats updated (569/574 pass)
- `docs/CURRENT_CLAUDE_HANDOFF.md` — this file updated

### Tests Run
- `tests/test_group15a_ai_log_car_track.py`: 56/56 pass
- Full suite: 569 pass / 5 skip / 0 fail (574 collected)

### AWR Summary (All Closed)

| AWR | Area | Result |
|-----|------|--------|
| AWR-058 | Strategy race_params (race_type/tuning/bop/avail_tyres) | CLOSED |
| AWR-059 | Practice worker car_id resolution | CLOSED |
| AWR-060 | Practice race_params bop | CLOSED |
| AWR-061 | avail_tyres throughout | CLOSED |
| AWR-062 | Driver feedback in practice AI | CLOSED |
| AWR-063 | Prev AI recs in practice prompt | CLOSED (DEF-P3-013 fixed Group 15A) |
| AWR-064 | PTT coaching car context | CLOSED |
| AWR-065 | PTT setup_advice live setup | CLOSED |
| AWR-066 | Timed race in race prompt | CLOSED |
| AWR-067 | build_car_setup race context | CLOSED |
| AWR-068 | _DATA_QUALITY_NOTE in ai_planner | CLOSED |
| AWR-069 | Strategy validation + warning banner | CLOSED |

### Open Defects Remaining (not Group 15 scope)

| ID | Priority | Title |
|----|----------|-------|
| DEF-P2-018 | P2 | Outlap row has no visual identification in Practice Review |
| DEF-P3-005 | P3 | Pit window is static, not recalculated on deviation |
| DEF-P3-007 | P3 | Disabled race type field not visually dimmed |
| DEF-P3-008 | P3 | Top speed target never populated from valid practice telemetry |

### Manual UAT Still Required
- AWR-063: Run Practice Analysis twice for same car+track. Second call's prompt (via GT7_AI_DEBUG=1) should contain "Previous AI Recommendations" section with the first response text.
- AWR-062: Submit driver feedback, run Practice Analysis → "Recent Driver Feedback" section appears in prompt.
- All other AWRs unchanged from prior session.

### Session: Group 17 (user: Group 16) — Corner-Level Telemetry Learning (2026-06-23)

#### New module: `data/corner_learning.py`
- `CornerIssue` dataclass: car_id, track, corner_id, lap_count, total_laps, issue_type, phase, severity, confidence, evidence, session_id, detected_at
- `ISSUE_TYPES` frozenset, `SETUP_ADVICE_MAP` dict (all major issue types → list[str])
- `_corner_id_from_xyz(x, z, bucket_m=100)` → XZ world-position bucket string
- PATH A: `detect_issues_from_lap_records(laps, car_id, track, session_id)` — from event_positions_json in lap_records; thresholds: ≥3 laps OR ≥30% of valid laps
- PATH B helpers: `detect_corner_events_from_frames(frames)` + `detect_issues_from_frame_data(per_lap_events, ...)`
- `merge_issues(path_a, path_b)` — PATH B overwrites PATH A for same corner+type
- `verify_fix(previous_issues, current_issues)` → dict of "corner_id:issue_type" → FIX_STATUS_*
- `build_corner_summary_for_prompt(issues, verifications, max_issues=6)` → concise AI prompt block
- `get_setup_advice(issue_type)` → list[str] from SETUP_ADVICE_MAP

#### `data/session_db.py` — schema v4
- `_DDL_V4` string: `corner_issues` table + index
- `_DDL` updated to include `_DDL_V4`
- `_migrate_v4()` — CREATE TABLE IF NOT EXISTS corner_issues + index
- `_migrate()` updated: `if version < 4:` block
- `get_session_laps()` SELECT now includes `event_positions_json` (needed for PATH A in worker)
- New methods: `save_corner_issues(issues)`, `get_corner_issues(car_id, track, session_id=0)`, `get_previous_corner_issues(car_id, track, exclude_session_id)`

#### `strategy/ai_planner.py`
- `_build_practice_prompt()` + `analyse_practice_session()` gain `corner_issues_summary: str = ""`; injected after per_lap_section
- `_build_race_prompt()` + `analyse_strategy()` gain `corner_issues_summary: str = ""`; injected after _fuel_trend_block

#### `strategy/driving_advisor.py`
- `build_coaching_response()`, `_build_coaching_prompt()` gain `corner_issues_summary`; added to `extra_sections`
- `build_setup_advice_response()`, `_build_setup_prompt()` gain `corner_issues_summary`; added to `extra_sections`
- `_build_combined_prompt()` gains `corner_issues_summary`; added to `extra_sections`

#### `ui/dashboard.py`
- `_run_practice_analysis()` worker: after `_per_lap_telem` query, calls `detect_issues_from_lap_records`, saves via `save_corner_issues`, loads previous via `get_previous_corner_issues`, runs `verify_fix`, builds `_corner_summary`, passes `corner_issues_summary=_corner_summary` to `analyse_practice_session()`
- `_run_ai_analysis()`: reads saved corner issues from DB before thread, reconstructs CornerIssue objects, builds `_strat_corner_summary`, passes to `analyse_strategy()`

#### Tests
- NEW: `tests/test_group17_corner_learning.py` — 64 tests (all pass)
- `tests/test_group16_per_lap_telemetry.py` — `test_user_version_is_3` updated to `>= 3`
- `MASTER_TESTING_REGISTER.md` — Group 17 section added
- `docs/PROJECT_STATE.md` — Group 17 row added; build stats updated (707/712 pass)

### Tests Run
- `tests/test_group17_corner_learning.py`: 64/64 pass
- Full suite: 707 pass / 5 skip / 0 fail (712 collected)

---

### Session: Group 18 — DEF-P3-014 Startup State Leak (2026-06-23)

**Defect:** `python main.py` with a previously used event printed:
```
[Strategy] plan set: 2 stints
[StateTracker] race config: timed, duration=40.0 min
[StateTracker] race config: timed, duration=40.0 min
```

**Root causes found and fixed:**

1. `main.py` lines 361–365 (removed): `strategy_engine.set_plan()` called at startup with `config["strategy"]["stops"]` — activated Live Race Engineer without user action
2. `main.py` lines 509–527 (removed): `tracker.set_race_config()` called from `config["race"]` / `config["strategy"]["race_type"]` before window created — first StateTracker print
3. `ui/dashboard.py` `_update_race_config()` (removed block): called `tracker.set_race_config()` during `_build_strategy_builder_tab()` on every startup — second StateTracker print
4. `ui/dashboard.py` `_on_event_set_active()` line 7801 (fixed): `from telemetry.tracker import RaceType` → `from telemetry.state import RaceType` (module `telemetry.tracker` does not exist — import silently caught by try/except, meaning `set_race_config()` never actually fired from the explicit activation path either)

**Architecture boundary**: `_on_event_set_active()` is now the ONLY path that calls `tracker.set_race_config()`.

**Tests:** `tests/test_group18_startup_no_plan.py` — 21 tests, all pass
**Full suite:** 728 pass / 5 skip / 0 fail (733 collected)

**Acceptance criteria met:**
- `python main.py` does NOT print `[Strategy] plan set` unless user activates a plan
- `python main.py` does NOT print `[StateTracker] race config` on startup
- Saved stops remain visible in Strategy Builder UI (populated in `dashboard.__init__` lines 482–487)
- Opening app after previously using a 40-min 2-stint plan does NOT reactivate it
- Duplicate StateTracker print eliminated (was 2, now 0 at startup)

### Session: Group 17A — Track Intelligence Seed Loader (2026-06-24)

#### New module: `data/track_intelligence.py`

- `TrackModellingStatus` enum — 9 values (`not_modelled`, `seed_only`, `telemetry_sampled`, `reference_path_built`, `segment_detected`, `user_reviewed`, `practice_refined`, `race_validated`, `engineer_grade`); helper methods: `is_ready_for_calibration()`, `is_ready_for_ai()`, `missing_calibration_requirements()`
- Dataclasses: `TrackSeedMetadata`, `CalibrationCarProfile`, `TrackLayoutSeed`, `TrackLocationSeed`, `TrackSeedLoadResult`
- `load_track_seed(yaml_path, force_reload)` — validates file exists, metadata, calibration cars, tracks, unknown statuses preserved, duplicates detected; caches on success from default path
- `get_track_locations()`, `get_track_layouts()`, `resolve_track_layout()`, `search_track_layouts()` — query helpers
- `build_seed_track_context_for_prompt(track_location_id, layout_id)` — AI prompt context block with seed data caveat for unmodelled layouts and calibration car boundary note
- Architecture boundary: Track Intelligence owns seed facts and modelling status only; no event/car/strategy state

#### New test file: `tests/test_group17a_track_intelligence.py`
- 63 tests, all pass (791/796 full suite)

#### New doc: `docs/TRACK_INTELLIGENCE_STARTER_MODEL.md`
- Architecture boundary, dataclass overview, enum maturity table, all 5 public functions, seed coverage table (18 layouts with full facts), calibration car facts, validation checks, next steps

#### Tests Run
- `tests/test_group17a_track_intelligence.py`: 63/63 pass
- Full suite: 791 pass / 5 skip / 0 fail (796 collected)

---

### Session: Group 17B — Track Modelling UI Foundation (2026-06-24)

#### New module: `ui/track_modelling_vm.py`
- Pure Python view model, no PyQt6 dependency — testable without QApplication
- `format_layout_facts(layout, loc)` — 27-row `(label, value)` list; None → "Unknown / needs calibration"
- `format_readiness(layout)` — readiness status rows with missing-step drill-down
- `format_calibration_car(car)` — Porsche 911 RSR key facts
- `get_seed_warning_text(layout)` — amber banner text for seed/partial layouts; empty for calibrated
- `is_seed_only(layout)` — True if `not_modelled` or `seed_only`
- `build_location_display_items(seed_result)` — sorted location combo items
- `build_layout_display_items(seed_result, loc_id)` — cascaded layout combo items
- `get_selected_location(seed_result, loc_id)` — resolve or None
- `get_selected_layout(seed_result, loc_id, lay_id)` — resolve or None
- `build_prompt_preview(seed_result, loc_id, lay_id)` — full AI prompt preview string
- `describe_seed_load_status(seed_result)` — one-line status summary
- `CALIBRATION_CAR_BOUNDARY_NOTE`, `SEED_WARNING_TEXT` constants

#### Modified: `ui/dashboard.py`
- Imports: `load_track_seed`, `search_track_layouts`, all `track_modelling_vm` helpers
- Tab 12 added: `self._tabs.addTab(self._build_track_modelling_tab(), "Track Modelling")`
- `_on_tab_changed(12)` → `self._tm_on_tab_shown()`
- `_build_track_modelling_tab()` — QSplitter with left selection panel + right detail panel
  - Left: search (QLineEdit + button → results QListWidget), location QComboBox → layout QComboBox, seed status label
  - Right: amber warning QGroupBox, layout facts QFormLayout (27 rows), readiness QFormLayout, calibration car QFormLayout + boundary note, AI prompt QPlainTextEdit (read-only)
- `_tm_on_tab_shown()` — lazy seed load on first tab visit; populates combos + car panel
- `_tm_populate_location_combo()`, `_tm_on_location_changed()`, `_tm_on_layout_changed()`
- `_tm_clear_detail_panels()`, `_tm_refresh_details(loc_id, lay_id)`
- `_tm_populate_calibration_car()`, `_tm_do_search()`, `_tm_on_search_result_selected()`
- `_tm_` prefix on all widgets to avoid namespace conflicts

#### New test file: `tests/test_group17b_track_modelling_ui.py`
- 101 tests, all pass
- 13 test classes covering all view model functions
- No PyQt6 widgets tested — pure view model layer only

#### Tests Run
- `tests/test_group17b_track_modelling_ui.py`: 101/101 pass
- Full suite: 892 pass / 5 skip / 0 fail (897 collected)

---

### Session: Group 17C — Calibration Lap Capture and Reference Path Builder (2026-06-24)

#### New module: `data/track_calibration.py`
Pure Python — no PyQt6 dependency.

**Data models:**
- `TelemetrySample` — one GT7 telemetry snapshot; `from_frame()` factory accepts duck-typed `TelemetryFrame`; `steering=None` (GT7 does not expose steering angle); `is_off_track` inferred from `road_plane_y < 0.5 AND speed > 20 kph`; `is_in_pit_lane=None` per sample
- `LapQualityResult` — `quality`, `reasons`, `sample_count`, `path_length_m`, `duration_ms`; `.is_usable` property
- `CalibrationLap` — lap_number, lap_time_ms, samples, quality, quality_reasons, path_length_m
- `CalibrationSession` — session_id, track_location_id, layout_id, calibration_car_id (default `porsche_911_rsr_991_2017`), started_at, source, laps, notes, modelling_status
- `ReferencePathPoint` — lap_progress, distance_along_lap_m, x, y, z, speed_kph_avg, source_lap_count
- `ReferencePath` — track/layout/car IDs, source_lap_count, points, confidence 0–1, built_at, warnings
- `CalibrationBuildResult` — success, reference_path, usable/rejected/low_confidence counts, errors, warnings
- `CalibrationLapQuality` enum: `USABLE`, `LOW_CONFIDENCE`, `REJECTED`
- `CalibrationSource` enum: `GT7_TELEMETRY_LIVE`, `IMPORTED_JSON`, `SYNTHETIC_TEST`

**Quality rules (reject):** too few samples (<50), all-zero xyz, coordinate jump >100 m, pit lane >10%, off-track >30%, duration outlier (>2× or <0.5× session median), path length outlier

**Distance / progress helpers:** `point_distance_3d`, `estimate_path_length`, `detect_coordinate_jumps`, `cumulative_distances`, `normalize_to_lap_progress`, `resample_to_buckets`

**Reference path builder:** `build_reference_path(session)` — 200 progress buckets, averaged per bucket across usable laps, cumulative distances, confidence = fill_rate × min(1, lap_count/5); requires ≥ 2 usable laps

**File I/O:** `export_reference_path_json`, `import_reference_path_json` — JSON under `data/track_models/`

**Constants:** `MIN_CALIBRATION_SAMPLES=50`, `MAX_JUMP_THRESHOLD_M=100`, `MAX_PIT_FRACTION=0.10`, `MAX_OFF_TRACK_FRACTION=0.30`, `N_PROGRESS_BUCKETS=200`, `MIN_USABLE_LAPS_FOR_PATH=2`, `PRIMARY_CALIBRATION_CAR_ID="porsche_911_rsr_991_2017"`

#### Modified: `ui/dashboard.py`
Added disabled placeholder calibration controls to Track Modelling tab right panel:
- "Start Calibration Session" button (disabled, tooltip explains deferral)
- "Stop Calibration Session" button (disabled)
- "Build Reference Path" button (disabled, tooltip: requires ≥ 2 usable laps)
- "No calibration session active" status label
Live telemetry wiring deferred — no existing dashboard architecture changed.

#### New test file: `tests/test_group17c_track_calibration.py`
- 102 tests, all pass
- 14 test classes covering all models, helpers, quality evaluator, path builder, file I/O, regression checks
- No PyQt6 dependency — fully headless

#### Decisions Made
- No DB migration — in-memory model + JSON file export sufficient for this group
- No corner/segment detection — deferred to Group 17D
- No live telemetry plumbing — deferred; existing architecture makes this safe when ready
- `steering` field always `None` — GT7 does not expose steering angle
- `is_in_pit_lane` always `None` per sample — no per-sample pit flag in GT7 packet

#### Tests Run
- `tests/test_group17c_track_calibration.py`: 102/102 pass
- Full suite: 994 pass / 5 skip / 0 fail (999 collected)

---

### Session: Group 17D — Live Telemetry Calibration Session Wiring (2026-06-24)

#### New module: `data/track_calibration_runtime.py`
Pure Python — no PyQt6 dependency.  Depends only on `data.track_calibration`.

**Adapter helpers:**
- `can_capture_calibration_sample(packet)` — duck-typed guard; returns False for paused/loading/off-track or any exception
- `infer_lap_number(packet, fallback=None)` — `laps_completed + 1` when ≥ 0; returns `fallback` when -1 (practice/qualifying with no lap count)
- `packet_to_calibration_sample(packet, lap_number)` — full GT7Packet → TelemetrySample mapping; `steering=None`, `is_in_pit_lane=None`; `is_off_track` from `road_plane_y < 0.5 AND speed > 20`; returns None on invalid/exception

**State enum:** `CalibrationCaptureState` — `INACTIVE` / `RECORDING` / `STOPPED` / `BUILT` / `ERROR`

**Controller:** `TrackCalibrationCaptureController`
- `start_session(track_location_id, layout_id, calibration_car_id)` — fails (ERROR) if IDs blank; resets all state
- `add_sample_from_packet(packet)` — RECORDING only; detects lap boundary from `laps_completed` change; calls `_close_current_lap()` at boundary; groups `TelemetrySample` objects into `CalibrationLap` objects
- `stop_session()` — flushes partial lap; transitions to STOPPED
- `evaluate_laps()` → `assess_session_laps(session)`
- `build_reference_path()` → `build_reference_path(session)`; transitions to BUILT
- `save_reference_path(output_dir)` → `export_reference_path_json(reference_path, output_dir)`
- `get_status_summary()` — 15-key dict for UI label refresh
- Properties: `can_start`, `can_stop`, `can_build`, `can_save`, `is_recording`
- Internal: `_close_current_lap()` — computes `lap_time_ms = t_end - t_start`, appends `CalibrationLap` to session

#### Modified: `ui/dashboard.py`
- `SignalBridge` gains `calibration_packet = pyqtSignal(object)` (after `ptt_status`)
- Import `TrackCalibrationCaptureController` from `data.track_calibration_runtime`
- Calibration group rebuilt: 4 live buttons (Start/Stop/Build/Save) with green hover style; 5 status labels (`_tm_lbl_sample_count`, `_tm_lbl_lap_info`, `_tm_lbl_build_info`, `_tm_lbl_cal_status`, `_tm_lbl_save_path`)
- `self._tm_controller = TrackCalibrationCaptureController()` stored on window after `self._tm_seed_result = None`
- `_tm_on_layout_changed()` calls `self._tm_update_cal_buttons()` after refresh
- `_tm_clear_detail_panels()` calls `self._tm_update_cal_buttons()`
- New methods: `_tm_update_cal_buttons()`, `_tm_update_cal_status()`, `_tm_on_calibration_packet()`, `_tm_start_session()`, `_tm_stop_session()`, `_tm_build_path()` (shows QMessageBox on fail), `_tm_save_path()` (shows QMessageBox on fail)
- `_connect_signals()` adds: `calibration_packet → _tm_on_calibration_packet`, 4 button click connections

#### Modified: `main.py`
- `_cal_pkt_counter = [0]` added as closure variable before `on_packet` definition
- In `on_packet()` after `recorder.record_frame()`: `if _cal_pkt_counter[0] % 6 == 0: bridge.calibration_packet.emit(packet)`; counter incremented mod 1000000
- Effective rate: 60 Hz / 6 = 10 Hz — same subsampling as `LapTelemetryRecorder`

#### New test file: `tests/test_group17d_calibration_runtime.py`
- 81 tests, all pass
- 10 test classes covering all helpers, state machine lifecycle, lap grouping, save/load, status summary, button properties, regression imports
- No PyQt6 dependency — fully headless

#### Decisions Made
- Controller is pure Python; `GT7Packet` accepted via duck-typing to avoid circular imports
- `steering` always `None` — GT7 protocol; `is_in_pit_lane` always `None` — no per-sample flag
- `laps_completed = -1` (practice mode) uses `fallback` parameter — controller defaults fallback to current lap number or 1
- `can_build` is a pre-filter (≥ 2 closed laps); the actual build can still fail quality evaluation
- QMessageBox shown on build/save failure so the user sees a clear error without leaving the tab

#### Tests Run
- `tests/test_group17d_calibration_runtime.py`: 81/81 pass
- Full suite: 1075 pass / 5 skip / 0 fail (1080 collected)

---

### Recommended Next Task
Group 17E — Wire `build_seed_track_context_for_prompt()` from `data/track_intelligence.py` into AI practice/coaching prompts (`strategy/driving_advisor.py` and `strategy/ai_planner.py`) so the AI receives track facts (sector count, elevation, corner types, known overtaking points) from the Track Modelling seed. Requires Track Modelling tab's selected layout to be passed through to the driving advisor call site.

---

### Session: Group 17O UAT Remediation (2026-06-25)

**Defects fixed:** DEF-17O-UAT-001, DEF-17O-UAT-002, DEF-17O-UAT-003

**DEF-17O-UAT-001 — Station Map panel shows "No track map loaded" after successful build**
- Root cause: `_tm_try_build_station_map()` read `ctrl._ref_path` (line 2737) but `TrackCalibrationCaptureController` has no `_ref_path` attribute. The reference path is stored at `ctrl._last_build_result.reference_path`.
- Fix: Changed `_tm_try_build_station_map(self)` to `_tm_try_build_station_map(self, ref_path=None)`. When `ref_path` is None, reads `ctrl._last_build_result.reference_path` (the correct attribute). Added a disk-load path in `_tm_detect_segments_safe()`: when loading calibration session from disk and station map is None, loads the saved reference path JSON and calls `_tm_try_build_station_map(ref_path=_ref)`.
- Imports added: `import_reference_path_json as _import_ref_path` from `data.track_calibration`.

**DEF-17O-UAT-002 — Segment Review still displays telemetry behaviour as track geometry**
- Root cause: `_create_seg_review(result)` at line 2917 was called with the full `SegmentDetectionResult` including `GEAR_ZONE`, `LIMITER_ZONE`, `FUEL_SAVING_CANDIDATE`, `KERB_OR_BUMP_CANDIDATE` — telemetry overlays that are not permanent track geometry.
- Fix: Added `_TELEMETRY_OVERLAY_SEG_TYPES` frozenset constant near imports; also imported `TrackSegmentType` as `_TrackSegmentType`. After `_create_seg_review(result)`, filters `self._tm_review_result.segments` to remove overlay types. Segment count label now shows geometry-only count with a note like "+3 telemetry overlays hidden".

**DEF-17O-UAT-003 — Daytona runtime still reports 5 corners despite seeded expected 12**
- Root cause: Corner count labels used `result.detected_corner_count` (old Group 17E telemetry detection, 5 corners for Daytona) instead of the station map seeded corner count (12, guaranteed by placeholder filling).
- Fix: In `_tm_detect_segments_safe()`, after detection succeeds, checks if `_tm_station_map` is available. If so, shows station map corner counts instead: `"{n_seeded} seeded corners | {n_detected_geo} curvature-detected | {n_placeholder} estimated"`. Falls back to old detection labels only if no station map is available.

**New test file:** `tests/test_group17o_uat_defects.py` — 23 tests across 3 defect classes
- `TestDef17OUAT001RefPathAttribute` (6 tests): verifies controller has no `_ref_path`, correct attribute chain works, station map builds from ref path, has_map=True produced, None/empty path → no_map
- `TestDef17OUAT002OverlayFiltering` (9 tests): overlay frozenset defined, all 4 overlay types in set, all geometry types NOT in set, filtering removes overlays, geometry preserved, review result filtering, overlay count calculation
- `TestDef17OUAT003DaytonaCornerCount` (8 tests): seed=12 → 12 seeded corners, station map is authoritative, placeholders fill gap, draw data has 12 labels, no-seed doesn't guarantee 12, status text includes count, detection result can differ from station map

**Files changed:**
- `ui/dashboard.py` — import fixes, `_TELEMETRY_OVERLAY_SEG_TYPES` constant, `_tm_try_build_station_map()` ref_path fix + optional param, disk-load station map build in `_tm_detect_segments_safe()`, overlay filtering, station map corner labels

**Full suite result: 2037 pass / 5 skip / 0 fail**

**Manual Daytona UAT steps after remediation:**
1. Start calibration at Daytona Road Course → drive 3+ clean laps → Stop → Build Reference Path.
2. Station Map panel must now render (no longer says "No track map loaded").
3. Save Reference Path → confirm map still shown.
4. Click Detect Segments → Segment Review table must NOT contain "Limiter approach", "Kerb/bump candidate", or "Gear zone" rows.
5. Summary label must read e.g. "12 seeded corners | 5 curvature-detected | 7 estimated" (not "Expected corners: 12 ≠ detected: 5").
6. Restart app, load Daytona → click Detect Segments → map builds from saved ref path, same corner summary shown.
