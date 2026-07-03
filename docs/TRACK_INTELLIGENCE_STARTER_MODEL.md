# Track Intelligence — Starter Model

## Overview

Track Intelligence is the NGR Pit Crew module that manages track facts for AI-assisted coaching. It provides a typed, validated seed loader for the `track_modelling_seed.yaml` catalogue and will grow into a full per-layout telemetry model as calibration laps are recorded.

## Architecture Boundary

Track Intelligence **owns**:
- Seed track facts (location, layout, length, corners, elevation, pit delta, flags)
- Modelling status per layout (how far along the calibration pipeline each layout is)
- Reference path metadata and segment modelling (future)
- AI prompt context blocks (what to inject into coaching prompts for a given layout)

Track Intelligence **does NOT own**:
- Event settings or race configuration
- Car setup state
- Strategy or stint planning state

## Module Location

```
data/track_intelligence.py
```

## Key Dataclasses

| Class | Purpose |
|-------|---------|
| `TrackSeedMetadata` | Schema name, version, purpose, track/layout counts |
| `CalibrationCarProfile` | Primary calibration car facts (Porsche 911 RSR '17) |
| `TrackLayoutSeed` | Single layout: length, corners, elevation, pit delta, flags, modelling status |
| `TrackLocationSeed` | Track location grouping layouts, with aliases and flags |
| `TrackSeedLoadResult` | Load result with errors, warnings, duplicate/unknown tracking |

## TrackModellingStatus Enum

Status values in maturity order (lowest → highest):

| Value | Description |
|-------|-------------|
| `not_modelled` | No telemetry recorded — seed data only (default for all new layouts) |
| `seed_only` | Seed catalogued, acknowledged as entry point |
| `telemetry_sampled` | At least one calibration lap recorded |
| `reference_path_built` | Reference path derived from telemetry |
| `segment_detected` | Straights / braking zones / corners auto-detected |
| `user_reviewed` | Driver has reviewed and confirmed segment boundaries |
| `practice_refined` | Model refined from multiple practice sessions |
| `race_validated` | Model validated against race-condition behaviour |
| `engineer_grade` | Full engineering sign-off |

### Helper methods

```python
status.is_ready_for_calibration()    # True if >= telemetry_sampled
status.is_ready_for_ai()             # True if >= segment_detected
status.missing_calibration_requirements()  # list of remaining steps
```

## Public Functions

```python
load_track_seed(yaml_path=None, force_reload=False) -> TrackSeedLoadResult
get_track_locations(yaml_path=None)  -> list[TrackLocationSeed]
get_track_layouts(yaml_path=None)    -> list[TrackLayoutSeed]   # flat list, all 121
resolve_track_layout(track_location_id, layout_id, yaml_path=None) -> TrackLayoutSeed | None
search_track_layouts(query, yaml_path=None) -> list[TrackLayoutSeed]  # case-insensitive
build_seed_track_context_for_prompt(track_location_id, layout_id, yaml_path=None) -> str
```

## Seed Coverage

| Stat | Value |
|------|-------|
| Track locations | 41 |
| Layout entries | 121 |
| Layouts with full GT Plus facts | 18 (see table below) |
| Layouts with null facts (catalogue only) | 103 |

### Layouts with populated facts

| Track | Layout | Length m | Corners | Elev m | Pit Δs | Rain | Night | 24h |
|-------|---------|---:|---:|---:|---:|:---:|:---:|:---:|
| Daytona International Speedway | Tri-Oval | 4023 | 4 | 10 | 14 | — | ✓ | ✓ |
| Daytona International Speedway | Road Course | 5729 | 12 | 8.4 | 25 | — | ✓ | ✓ |
| Deep Forest Raceway | Full Course | 4253 | 18 | 50 | 15 | — | ✓ | — |
| Deep Forest Raceway | Full Course Reverse | 4253 | 18 | 50 | 15 | — | ✓ | — |
| Fuji International Speedway | Full Course | 4563 | 16 | 40 | 17 | ✓ | — | — |
| Fuji International Speedway | Short Course | 4526 | 14 | 40 | 17 | ✓ | — | — |
| High Speed Ring | Full Course | 4345 | 6 | 8.5 | 10 | ✓ | — | — |
| High Speed Ring | Full Course Reverse | 4345 | 6 | 8.5 | 10 | ✓ | — | — |
| Mount Panorama Circuit | Full Course | 6213 | 23 | 174 | 24 | — | ✓ | ✓ |
| Red Bull Ring | Full Course | 4318 | 10 | 65.5 | 25 | ✓ | ✓ | — |
| Red Bull Ring | Short Track | 2336 | 6 | 32.4 | 25 | ✓ | ✓ | — |
| Michelin Raceway Road Atlanta | Full Course | 4088 | 12 | 38 | 10 | — | ✓ | ✓ |
| Circuit de Spa-Francorchamps | Full Course | 7004 | 21 | 104 | 25 | ✓ | — | — |
| Circuit de Spa-Francorchamps | 24h Layout | 7004 | 21 | 104 | 35 | ✓ | ✓ | ✓ |
| Trial Mountain Circuit | Full Course | 5434 | 15 | 58 | 26 | — | ✓ | — |
| Trial Mountain Circuit | Full Course Reverse | 5434 | 15 | 58 | 26 | — | ✓ | — |
| Watkins Glen International | Long Course | 5423 | 11 | 41.1 | 10 | — | ✓ | — |
| Watkins Glen International | Short Course | 3942 | 7 | 10.7 | 10 | — | ✓ | — |

## Primary Calibration Car

**Porsche 911 RSR (991) '17**
- Class: Gr.3 | Drivetrain: MR | Engine: Flat-6 NA
- Power: 509 BHP @ 8100 rpm
- Torque: 49.8 kgf·m @ 6000 rpm
- Weight: 1243 kg | Tyres: RH | PP: 720.74

**Architecture rule:** Track geometry must remain car-independent. Braking points, gear usage, throttle behaviour, tyre stress, and corner-exit drive from Porsche calibration laps are stored as Porsche RSR behaviour — not universal track truth.

## Validation Checks Performed on Load

1. File exists
2. Required metadata fields present (`schema_name`, `schema_version`, `generated_utc`)
3. At least one `calibration_car_profiles` entry
4. Non-empty `tracks` list
5. Unknown `modelling_status` values preserved and reported in `unknown_modelling_statuses`
6. Duplicate `layout_id` values detected and reported in `duplicate_layout_ids`
7. Layout ID prefix matches parent `track_location_id` (warning if not)
8. Alias clash with other location IDs (warning if found)

## Caching

`load_track_seed()` caches the result after first successful load from the default path. Subsequent calls return the same object. Use `force_reload=True` to bypass. Passing a custom `yaml_path` never writes to the global cache (useful for testing).

## AI Prompt Integration

```python
ctx = build_seed_track_context_for_prompt("fuji_international_speedway",
                                          "fuji_international_speedway__full_course")
# Inject ctx into your AI prompt before coaching/setup questions
```

For `not_modelled` and `seed_only` layouts the output includes an explicit **DATA CAVEAT** block instructing the AI to use hedged language and not state corner geometry as fact.

## Group 17B — Track Modelling UI Foundation

**Tab:** "Track Modelling" (tab index 12 in `ui/dashboard.py`). Added as a QSplitter layout.

### View Model Layer

`ui/track_modelling_vm.py` — pure Python, no PyQt6 dependency. Tested without a QApplication.

| Function | Purpose |
|----------|---------|
| `format_layout_facts(layout, loc)` | `(label, value)` pairs for the facts panel; all 27 fields always shown; `None` → `UNKNOWN_VALUE` |
| `format_readiness(layout)` | Readiness status rows including per-step detail |
| `format_calibration_car(car)` | Calibration car key facts |
| `get_seed_warning_text(layout)` | Amber warning text for seed/partial-telemetry layouts |
| `is_seed_only(layout)` | True if `not_modelled` or `seed_only` |
| `build_location_display_items(seed_result)` | Sorted `(display, id)` list for location combo |
| `build_layout_display_items(seed_result, loc_id)` | `(display, id)` list for layout combo |
| `get_selected_location(seed_result, loc_id)` | Resolve location or None |
| `get_selected_layout(seed_result, loc_id, lay_id)` | Resolve layout or None |
| `build_prompt_preview(seed_result, loc_id, lay_id)` | Full seed-only AI prompt preview string |
| `describe_seed_load_status(seed_result)` | One-line seed load summary for the status panel |

### UI Panels (right-to-left split)

**Left panel (selection):**
- Search bar → `search_track_layouts(query)` → results list (double-click selects)
- Track Location QComboBox → Layout QComboBox (cascades)
- Seed Status label (green on success, red on failure)

**Right panel (details, scrollable):**
- Amber "Seed Data Warning" QGroupBox (hidden for `segment_detected`+)
- "Layout Facts" QGroupBox — 27 QFormLayout rows, green for known / amber for unknowns
- "Calibration Readiness" QGroupBox — status, seed-only flag, readiness flags, missing steps
- "Calibration Car — Porsche 911 RSR (991) '17" QGroupBox — car facts + amber boundary note
- "AI Prompt Preview" QGroupBox — read-only QPlainTextEdit showing `build_seed_track_context_for_prompt()` output

### Tests

`tests/test_group17b_track_modelling_ui.py` — 101 tests, all pass.

| Class | Tests |
|-------|-------|
| `TestFormatLayoutFacts` | 21 |
| `TestFormatReadiness` | 14 |
| `TestFormatCalibrationCar` | 9 |
| `TestGetSeedWarningText` | 7 |
| `TestIsSeedOnly` | 5 |
| `TestBuildLocationDisplayItems` | 8 |
| `TestBuildLayoutDisplayItems` | 7 |
| `TestGetSelectedLocation` | 3 |
| `TestGetSelectedLayout` | 4 |
| `TestBuildPromptPreview` | 6 |
| `TestDescribeSeedLoadStatus` | 7 |
| `TestBoundaryNote` | 3 |
| `TestSeedWarningText` | 3 |

## Group 17C — Calibration Lap Capture and Reference Path Builder

**New module:** `data/track_calibration.py` — pure Python, no PyQt6 dependency.

### Key Data Models

| Class | Purpose |
|-------|---------|
| `TelemetrySample` | One telemetry snapshot; `from_frame()` factory maps `TelemetryFrame` duck-typed; optional `steering` is always `None` (not in GT7 packet) |
| `LapQualityResult` | Quality assessment output: `quality`, `reasons`, `sample_count`, `path_length_m`, `duration_ms` |
| `CalibrationLap` | One lap: samples, quality rating, quality reasons, path length |
| `CalibrationSession` | All laps for one layout: `track_location_id`, `layout_id`, `calibration_car_id`, `laps` |
| `ReferencePathPoint` | One averaged path point: `lap_progress`, `distance_along_lap_m`, `x/y/z`, `speed_kph_avg`, `source_lap_count` |
| `ReferencePath` | Built reference: track/layout IDs, car ID, list of `ReferencePathPoint`, confidence 0–1, warnings |
| `CalibrationBuildResult` | Build outcome: success, reference_path, usable/rejected/low-confidence counts, errors, warnings |

### Quality Rules (`CalibrationLapQuality`)

| Status | Criteria |
|--------|---------|
| `REJECTED` | Too few samples (< 50), all-zero x/y/z, coordinate jump > 100 m, pit lane > 10%, off-track > 30%, duration outlier vs session median (>2× or <0.5×), path length outlier vs session median |
| `LOW_CONFIDENCE` | Partial zero-xyz samples (not all) |
| `USABLE` | None of the above |

### Reference Path Builder — `build_reference_path(session) -> CalibrationBuildResult`

1. Evaluate all laps with session-level medians via `assess_session_laps()`
2. Select only `USABLE` laps; require ≥ 2
3. Normalise each lap to [0.0, 1.0] progress from cumulative 3D distance
4. Divide each lap into 200 progress buckets
5. Merge buckets across laps; average x/y/z/speed per bucket
6. Compute cumulative `distance_along_lap_m` from averaged positions
7. Confidence = `fill_rate × min(1.0, lap_count / 5)`

### Distance / Progress Helpers

| Function | Purpose |
|----------|---------|
| `point_distance_3d(x1,y1,z1, x2,y2,z2)` | Euclidean 3D distance |
| `estimate_path_length(samples)` | Sum of consecutive 3D distances |
| `detect_coordinate_jumps(samples, threshold_m)` | Teleport/reset detection |
| `cumulative_distances(samples)` | Per-sample cumulative path distance |
| `normalize_to_lap_progress(samples)` | [0.0, 1.0] per-sample progress |
| `resample_to_buckets(samples, n_buckets)` | Partition into progress buckets |

### File I/O

- `export_reference_path_json(path, output_dir)` → writes `data/track_models/<loc>__<lay>.reference_path.json`
- `import_reference_path_json(json_path)` → loads and reconstructs `ReferencePath`

### Off-track Detection

- `is_off_track` on `TelemetrySample` is computed from `road_plane_y < 0.5 AND speed > 20 kph` (same threshold as `telemetry/recorder.py`)
- `is_in_pit_lane` is always `None` per sample — no GT7 packet flag for pit lane; tracked at session level only

### UI Integration (Group 17C)

Added to Track Modelling tab right panel: disabled placeholder controls:
- **Start Calibration Session** (disabled — requires live GT7 telemetry wiring)
- **Stop Calibration Session** (disabled)
- **Build Reference Path** (disabled — requires ≥ 2 usable laps)
- Status label: "No calibration session active"
- Tooltip on each button explains the deferral reason

### Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| No corner/segment detection | Deferred to Group 17D or later |
| No DB migration | In-memory model sufficient for this group; JSON export for persistence |
| No live telemetry wiring | Existing telemetry architecture works but wiring requires careful session-boundary integration |
| No steering angle | GT7 packet does not expose steering angle |
| `calibration_car_id` default | Always `porsche_911_rsr_991_2017` |

### Tests

`tests/test_group17c_track_calibration.py` — 102 tests, all pass.

| Class | Tests |
|-------|-------|
| `TestTelemetrySample` | 11 |
| `TestCalibrationSession` | 6 |
| `TestPointDistance3d` | 5 |
| `TestEstimatePathLength` | 5 |
| `TestDetectCoordinateJumps` | 7 |
| `TestCumulativeDistances` | 6 |
| `TestNormalizeToLapProgress` | 6 |
| `TestResampleToBuckets` | 7 |
| `TestEvaluateLapQuality` | 20 |
| `TestBuildReferencePath` | 18 |
| `TestFileExportImport` | 6 |
| `TestAssessSessionLaps` | 4 |
| `TestCalibrationBuildResult` | 3 |
| `TestRegressionImports` | 4 |

---

## Group 17D — Live Telemetry Calibration Session Wiring

**New module:** `data/track_calibration_runtime.py` — pure Python, no PyQt6 dependency.

### Adapter Helpers (pure functions)

| Function | Purpose |
|----------|---------|
| `can_capture_calibration_sample(packet)` | Guard; False for paused/loading/off-track or exception |
| `infer_lap_number(packet, fallback)` | `laps_completed + 1` when ≥ 0; fallback when -1 (practice mode) |
| `packet_to_calibration_sample(packet, lap_number)` | GT7Packet → TelemetrySample; steering=None; pit=None; off-track from road_plane_y heuristic |

### State Machine

`CalibrationCaptureState` enum: `INACTIVE`, `RECORDING`, `STOPPED`, `BUILT`, `ERROR`

`TrackCalibrationCaptureController` — all methods called from Qt main thread via signal slots; no locking.

| Method | Behaviour |
|--------|-----------|
| `start_session(loc, layout, car)` | Creates `CalibrationSession`; fails to ERROR if IDs blank |
| `add_sample_from_packet(packet)` | RECORDING only; detects lap boundary; groups into `CalibrationLap` |
| `stop_session()` | Flushes partial lap; → STOPPED |
| `evaluate_laps()` | Delegates to `assess_session_laps()` |
| `build_reference_path()` | Delegates to `build_reference_path()`; → BUILT |
| `save_reference_path(output_dir)` | Delegates to `export_reference_path_json()` |
| `get_status_summary()` | 15-key dict for UI label refresh |

| Property | Meaning |
|----------|---------|
| `can_start` | Not currently RECORDING |
| `can_stop` | Currently RECORDING |
| `can_build` | STOPPED or BUILT with ≥ MIN_USABLE_LAPS_FOR_PATH closed laps |
| `can_save` | Last build succeeded and reference_path is populated |
| `is_recording` | RECORDING |

### Architecture

**Data flow:** `on_packet()` (UDP thread, 60 Hz) → `_cal_pkt_counter % 6 == 0` → `bridge.calibration_packet.emit(packet)` → Qt signal cross-thread delivery → `_tm_on_calibration_packet` slot (Qt main thread) → `controller.add_sample_from_packet(packet)` → `_tm_update_cal_status()`

**Lap boundary detection:** When `infer_lap_number(packet)` changes, `_close_current_lap()` flushes current samples into a `CalibrationLap` and appends it to `session.laps`. `lap_time_ms = last_timestamp - first_timestamp` within the lap.

**GT7 limitations preserved:**
- `steering = None` always — GT7 protocol does not expose steering angle
- `is_in_pit_lane = None` always — no per-sample pit lane flag in GT7 packet
- `laps_completed = -1` in practice/qualifying — controller uses fallback (current lap number or 1)

### UI Changes (dashboard.py)

- `SignalBridge.calibration_packet = pyqtSignal(object)` — cross-thread 10 Hz packet delivery
- 4 live buttons: Start / Stop / Build / Save (green style; state-driven enable/disable)
- 5 status labels: sample count, lap info, build info, session status, save path
- `_tm_controller = TrackCalibrationCaptureController()` stored on `MainWindow`
- `_tm_update_cal_buttons()` called from layout/clear panel changes and all button handlers
- Build/save failures shown via `QMessageBox.warning()` — user sees the error without leaving the tab

### main.py Changes

```python
_cal_pkt_counter = [0]

def on_packet(data: bytes) -> None:
    ...
    recorder.record_frame(packet, tracker.laps_recorded)
    if _cal_pkt_counter[0] % 6 == 0:
        bridge.calibration_packet.emit(packet)
    _cal_pkt_counter[0] = (_cal_pkt_counter[0] + 1) % 1000000
```

### Test Coverage

`tests/test_group17d_calibration_runtime.py` — 81 tests, all pass.

| Class | Tests |
|-------|-------|
| `TestCanCaptureSample` | 7 |
| `TestInferLapNumber` | 7 |
| `TestPacketToCalibrationSample` | 10 |
| `TestCalibrationCaptureState` | 1 |
| `TestControllerStart` | 8 |
| `TestControllerSampling` | 5 |
| `TestControllerLapGrouping` | 7 |
| `TestControllerStop` | 4 |
| `TestControllerBuild` | 8 |
| `TestControllerSave` | 3 |
| `TestControllerStatusSummary` | 6 |
| `TestButtonStateProperties` | 10 |
| `TestControllerEvaluateLaps` | 2 |
| `TestRegressionImports` | 4 |

---

## Group 17E — Automatic Track Segment Detection

**New module:** `data/track_segment_detection.py` — pure Python, no PyQt6 dependency.

**Segment types (12):** `start_finish`, `straight`, `braking_zone`, `corner_entry`, `apex_zone`, `corner_exit`, `traction_zone`, `gear_zone`, `limiter_zone`, `fuel_saving_candidate`, `kerb_or_bump_candidate`, `unknown`

**Detection pipeline:**

1. `detect_segments_from_lap(lap, config)` — single-lap detection:
   - Computes `normalize_to_lap_progress()` from cumulative XZ distance
   - Smoothed speed → local minima (apex candidates, drop ≥ 15 kph)
   - Per apex: walk back for braking onset (brake > 0.15 or speed > apex+15), walk forward for throttle restore (throttle > 0.75 + speed recovering)
   - Emits `braking_zone`, `corner_entry`, `apex_zone`, `corner_exit`, `traction_zone` per corner
   - Fills gaps with `straight` or `fuel_saving_candidate` (span ≥ 8% + avg throttle > 70%)
   - Heading/curvature from X/Z position delta → corner direction; `UNKNOWN` when no position variation
   - Confidence: LOW (speed-only) or MEDIUM (curvature evidence)

2. `detect_track_segments(session, reference_path, layout_seed, config)` — multi-lap:
   - USABLE laps only; REJECTED excluded
   - `_cluster_apex_progress()` groups apex candidates within 2.5% lap progress across laps
   - Clusters appearing in ≥ 2 laps → confirmed corners; < 2 laps → excluded with warning
   - `layout_seed.corners_expected` → count mismatch warning only (never invents corners)
   - Auxiliary: `_detect_gear_zones_from_lap`, `_detect_limiter_zones_from_lap`, `_detect_kerb_candidates_multi_lap`, fuel-save candidates from inter-corner gaps
   - Corner numbering: `assign_corner_numbers()` assigns T1/T2… by progress order; mismatch warning when |detected − expected| > 2

**Car-specific vs track-geometry boundary (critical):**
- `calibration_car_id` tagged on: `braking_zone`, `corner_entry`, `traction_zone`, `limiter_zone`, `fuel_saving_candidate`, `gear_zone`
- NOT tagged: `apex_zone`, `straight`, `corner_exit`, `kerb_or_bump_candidate`
- All car-tagged segments carry: *"Car-specific — Porsche RSR behaviour, not universal track truth"*

**JSON I/O:** `export_segment_detection_json()` / `import_segment_detection_json()` — schema `segment_detection_result_v1`

**UI:** "Detect Segments" button (enabled when `ctrl.can_save`); 3 status labels in Track Modelling Calibration group

**Test coverage:** 99 tests in `tests/test_group17e_track_segment_detection.py` — 22 test classes

---

## Group 17F — Segment Review and Track Model Approval

**New module:** `data/track_segment_review.py` — pure Python, no PyQt6 dependency.

**Review statuses (8):** `unreviewed`, `confirmed`, `renamed`, `split_required`, `merge_required`, `rejected`, `needs_more_laps`, `engineer_validated`

**Review actions (7):** `confirm`, `rename`, `reject`, `mark_needs_more_laps`, `mark_split_required`, `mark_merge_required`, `promote_engineer_validated`

**Dataclasses:**
- `ReviewedTrackSegment` — original detection fields (preserved) + review state (`review_status`, `reviewed_display_name`, `review_notes`, `reviewed_at`, `last_action`); `display_name` property returns override if set, else original; `is_reviewed` property is True when status ≠ UNREVIEWED
- `TrackModelReviewResult` — detection metadata + list of `ReviewedTrackSegment`; `detection_warnings` preserved verbatim; `last_reviewed_at` updated on every action

**Review workflow:**
1. `detect_track_segments()` → `SegmentDetectionResult`  (Group 17E)
2. `create_review_from_detection(result)` → `TrackModelReviewResult`  (all UNREVIEWED)
3. `confirm_segment / rename_segment / reject_segment / mark_*` per segment
4. `review_completion_pct(review)` → float (0–100%)
5. `is_ai_ready(review)` → `(bool, list[str] blockers)`
6. `export_review_json(review)` → JSON file in `data/track_models/`

**AI-ready criteria (all required):**
- At least one segment exists
- All `apex_zone` segments are reviewed (not UNREVIEWED)
- No segment is `needs_more_laps`
- No segment is `split_required` or `merge_required`
- Each required type is present in detection: `straight`, `braking_zone`, `apex_zone`, `corner_exit`

**Design decisions:**
- `rename_segment()` ignores blank names (status stays UNREVIEWED)
- `promote_engineer_validated()` only works on CONFIRMED segments (prevents bypassing confirm step)
- Detection warnings are never cleared — always visible in `review.detection_warnings`
- Car-specific segment warnings (Porsche RSR) preserved on each `ReviewedTrackSegment.warnings`
- Engineer-validated is a future maturity level; NOT required for AI-ready

**JSON persistence:**
- Schema: `track_model_review_result_v1`
- Filename: `<track_location_id>__<layout_id>__reviewed_segments__<session_id>.json`
- Dir: `data/track_models/` (shared with detection results)
- `import_review_json()` raises `FileNotFoundError` or `ValueError` on bad input — never silently returns bad data

**`ui/track_modelling_vm.py` additions:**
- `format_segment_row(seg)` → dict for table display (name, turn, type, progress, confidence, laps, status, warnings)
- `format_review_summary(review)` → dict for approval panel (detected/reviewed/confirmed/rejected/needs-more-laps counts, completion%, ai_ready, blockers)
- `get_review_button_states(review, selected_segment_id)` → dict (confirm/rename/reject/needs_more_laps/split_required/merge_required/save enabled states)

**`ui/dashboard.py` additions:**
- Import block for `track_segment_review` action functions and vm helpers
- "Segment Review" QGroupBox: QTableWidget (8 cols, read-only, single-row selection), 6 action buttons (Confirm/Rename/Reject/Needs More Laps/Split Required/Merge Required), "Save Reviewed Model" button
- "Review Approval" QGroupBox: stat labels (detected/reviewed/confirmed/rejected/needs-laps/completion%/ai-ready/blockers)
- `_tm_detection_result`, `_tm_review_result`, `_tm_selected_segment_id` instance variables
- `_tm_detect_segments()` now auto-creates `TrackModelReviewResult` on detection success
- Methods: `_tm_refresh_seg_table`, `_tm_on_seg_selected`, `_tm_refresh_review_buttons`, `_tm_refresh_approval_panel`, `_tm_review_confirm`, `_tm_review_rename`, `_tm_review_reject`, `_tm_review_needs_laps`, `_tm_review_split`, `_tm_review_merge`, `_tm_review_save`
- Signal connections for all new buttons

**Deferred:**
- Graphical split/merge segment editing (currently review flags only)
- Integration of reviewed segments into Setup Builder, Strategy Builder, Practice Analysis, Live Race Engineer prompts (Group 17G+)
- Promotion of `TrackLayoutSeed.modelling_status` to `segment_detected` after review save

**Test coverage:** 122 tests in `tests/test_group17f_segment_review.py` — 14 test classes

---

## Group 17G — Approved Track Model Resolver and Modelling Status Promotion

**New module:** `data/track_model_resolver.py` (pure Python, no PyQt6)

**Enums:**
- `TrackModelSourceType` (6 values): `seed_only`, `detected_unreviewed`, `reviewed_model`, `ai_ready_reviewed_model`, `engineer_validated_model`, `missing`
- `TrackModelResolutionStatus` (6 values): `found`, `found_with_warnings`, `seed_only_fallback`, `not_ai_ready`, `missing`, `error`

**Dataclasses:**
- `ResolvedTrackModel` — best model for a track/layout with source_type, modelling_status, ai_ready flag, segment counts, blockers, warnings, source_path, reviewed_model, seed_layout
- `TrackModelResolverResult` — full resolution result with resolved_model, all_candidate_paths, errors, warnings

**Discovery functions:**
- `list_reviewed_track_models(base_dir)` → all `*__reviewed_segments__*.json` files, newest first
- `find_reviewed_models_for_layout(loc, layout, base_dir)` → filtered by prefix, newest first
- `load_reviewed_track_model(path)` → delegates to `import_review_json`

**Core resolver:**
- `resolve_best_track_model(loc, layout, base_dir)` — returns best available model:
  1. Load all candidate files for this loc/layout
  2. Classify each by source type (engineer_validated > ai_ready > reviewed > seed > missing)
  3. When maturity is equal, prefer newest by `created_at` timestamp (filename as tie-breaker)
  4. Malformed files silently skipped; errors recorded in `TrackModelResolverResult.errors`
  5. If no reviewed model found, fall back to seed layout with appropriate warnings
  6. If no seed entry either, return MISSING

**Model maturity classification:**
- `ENGINEER_VALIDATED_MODEL`: any segment has `SegmentReviewStatus.ENGINEER_VALIDATED`
- `AI_READY_REVIEWED_MODEL`: `is_ai_ready()` returns True
- `REVIEWED_MODEL`: reviewed file exists but neither above
- `SEED_ONLY`: no reviewed file; seed entry exists
- `MISSING`: no reviewed file and no seed entry

**AI prompt context builder (not wired to AI yet):**
- `build_resolved_track_context_for_prompt(loc, layout, base_dir)` → compact string:
  - Missing: "MISSING" message
  - Seed-only: `build_seed_track_context_for_prompt()` + "No reviewed track model" note
  - Reviewed model: model source, modelling status, AI-ready, segment summary, confirmed segment list, car-behaviour boundary note, blockers (if not AI-ready), warnings (capped at 5)

**Modelling status in JSON schema (Group 17G extension):**
- `TrackModelReviewResult.modelling_status: Optional[str] = None` (new optional field)
- `export_review_json()` now computes and writes `modelling_status`:
  - any `ENGINEER_VALIDATED` segment → `"engineer_grade"`
  - `is_ai_ready()` = True → `"user_reviewed"`
  - otherwise → `"segment_detected"`
- `import_review_json()` reads `modelling_status` if present; old files get `None` (backward-compatible)
- Resolver uses persisted status if present; recomputes from review data if absent (old files)

**`ui/track_modelling_vm.py` addition:**
- `format_resolver_summary(resolver_result)` → dict with 8 keys: source_type (human label), modelling_status, ai_ready, blockers, model_path, warnings, resolution_status, candidate_count

**`ui/dashboard.py` changes:**
- Import: `resolve_best_track_model as _resolve_track_model`, `format_resolver_summary as _format_resolver_summary`
- `_tm_resolver_result` instance variable
- "Resolver Status" QGroupBox (after Review Approval): 5 labels (source, status, AI-ready, candidates, latest file) + blockers label + warnings label
- `_tm_review_save()` now calls `_tm_refresh_resolver()` after successful save
- `_tm_on_layout_changed()` now calls `_tm_refresh_resolver()` when layout selected (shows pre-existing models)
- `_tm_refresh_resolver()` — resolves model, formats summary, updates all resolver labels

**Design decisions:**
- Do NOT mutate the public seed YAML — modelling status is persisted in the reviewed JSON only
- Seed-only fallback always shows warnings — never silently presents seed facts as validated
- Car-behaviour boundary note always included in prompt context
- Malformed files never crash resolution — errors recorded and skipped
- Prompt context builder is not wired to Setup Builder / Strategy Builder / AI yet (Group 17H+)

**Deferred:**
- Graphical split/merge editing (currently review flags only)
- Integration of resolved context into Setup Builder, Strategy Builder, Practice Analysis, Live Race Engineer (Group 17H+)
- Auto-detection of track/layout from telemetry

**Test coverage:** 68 tests in `tests/test_group17g_track_model_resolver.py` — 13 test classes

---

## Group 17H — Track Intelligence AI Prompt Integration

**New module:** `strategy/track_context_prompt.py` — thin helper, no PyQt6, no state

**Public function:**
```python
get_track_context_for_ai(track_location_id: str | None, layout_id: str | None) -> str
```
- If either ID is missing: returns compact `"Track Intelligence unavailable: no selected track/layout was provided."` warning
- If present: delegates to `build_resolved_track_context_for_prompt()`
- On any resolver exception: returns safe error note, never raises

**`RaceParams` (strategy/ai_planner.py):**
- Added `track_location_id: str = ""` and `layout_id: str = ""` optional fields
- Populated from `config["strategy"]["track_location_id"]` / `["layout_id"]` in dashboard.py

**`ai_planner.py` prompt injection:**
- `_build_race_prompt()` — `track_context` parameter; section injected before `## Practice lap times`
- `_build_practice_prompt()` — `track_context` parameter; section injected before `## Practice lap times`
- `_build_setup_from_scratch_prompt()` — `track_context` parameter; section injected after race conditions block
- `build_car_setup()` — `track_location_id` and `layout_id` parameters; calls `get_track_context_for_ai()`
- `analyse_strategy()` — resolves track context before building prompt; `structured_payload` includes `track_context_included`, `track_location_id`, `layout_id` for debug logging
- `analyse_practice_session()` — same structured_payload additions

**`driving_advisor.py` prompt injection:**
- `DrivingAdvisor._get_track_intelligence_context()` — reads `config["strategy"]["track_location_id"]` / `["layout_id"]`; delegates to `get_track_context_for_ai()`; never raises
- `_build_coaching_prompt()` — `track_intel_block` prepended to `extra_sections`
- `_build_setup_prompt()` — same
- `_build_combined_prompt()` — same
- `_build_feeling_prompt()` — not wired (driver-feeling prompt is car-specific, not track-specific; deferred)

**`ui/dashboard.py` changes:**
- `_tm_on_layout_changed()` — stores `loc_id` / `lay_id` into `config["strategy"]["track_location_id"]` / `["layout_id"]` when Track Modelling layout is selected
- `_run_ai_analysis()` race_params dict — includes `track_location_id` and `layout_id` from config
- `_run_practice_analysis()` race_params dict — includes `track_location_id` and `layout_id` from config; debug print updated to include track context presence
- `_run_build_setup()` — reads `_track_loc_id` / `_layout_id_build` from config; passes to `build_car_setup()`

**AI debug logging (`GT7_AI_DEBUG=1`):**
- `analyse_strategy` and `analyse_practice_session`: `structured_payload` now includes `track_context_included: bool`, `track_location_id: str|None`, `layout_id: str|None`
- `build_car_setup`: same fields in `structured_payload`
- `_run_practice_analysis` debug print: includes `track_context_included=`, `track_location_id=`, `layout_id=`

**Source of truth for track/layout IDs:**
- Set when user selects a location/layout in the Track Modelling tab
- Stored in `config["strategy"]["track_location_id"]` / `["layout_id"]`
- NOT inferred from event track display name
- NOT auto-detected from telemetry
- If not set → AI receives "Track Intelligence unavailable" warning in all prompts

**Prompt section injection per AI caller:**

| Caller | Section injected | Location in prompt |
|---|---|---|
| Race strategy | `## Track Intelligence\n...` | After race params, before practice lap times |
| Practice analysis | `## Track Intelligence\n...` | After race params, before practice lap times |
| Setup from scratch | `## Track Intelligence\n...` | After race conditions block |
| Coaching (DrivingAdvisor) | `## Track Intelligence\n...` | In `extra_sections` (before event/feedback/prev_ai) |
| Setup advice (DrivingAdvisor) | `## Track Intelligence\n...` | In `extra_sections` |
| Combined setup (DrivingAdvisor) | `## Track Intelligence\n...` | In `extra_sections` |

**Seed-only and non-AI-ready behaviour:**
- Seed-only: prompt receives seed context + explicit "seed data only — NOT validated" warning
- Not AI-ready: prompt receives reviewed segment list + explicit "NOT AI-READY — blockers" section
- Missing: prompt receives "MISSING — no seed entry and no reviewed model" message
- All cases include the Porsche boundary note where applicable

**Deferred:**
- Live current-segment lookup
- Telemetry-to-segment issue enrichment → **implemented in Group 17I**
- Graphical split/merge editing
- Track auto-detection from telemetry
- Wiring layout_id from Event Planner directly (currently only from Track Modelling tab selection)
- `_build_feeling_prompt` track context injection

**Test coverage:** 56 tests in `tests/test_group17h_track_context_prompt.py` — 16 test classes

---

## Group 17I — Telemetry Issue to Segment Enrichment

**New module:** `data/track_issue_enrichment.py` — pure Python, no PyQt6

**Purpose:** Map existing telemetry issue positions (XYZ, lap_progress, corner_id grid buckets) to reviewed track segments so AI prompts can name specific corners when advising on braking/traction/oversteer issues.

**Core function:** `enrich_telemetry_issues(raw_issues, loc_id, lay_id, base_dir) -> TrackIssueEnrichmentResult`
- Resolves reviewed track model via `resolve_best_track_model()` (Group 17G)
- Loads reference path file for XYZ→lap_progress conversion
- Matching priority: segment_id exact → lap_progress range → distance_along_lap_m → XYZ nearest → nearest midpoint fallback → UNRESOLVED

**Matching confidence:** Based on model maturity (engineer_validated→HIGH, reviewed→MEDIUM, seed→LOW, missing→UNRESOLVED) degraded by segment review status (REJECTED→UNRESOLVED, NEEDS_MORE_LAPS→LOW) and match method (`nearest` downgrades one level).

**Adapters:**
- `issues_from_lap_stats(laps)` — converts `LapStats` position lists to `RawTelemetryIssue` (lock_up, wheelspin, oversteer, snap_throttle, over_braking)
- `issues_from_corner_issues(cis)` — converts `CornerIssue` objects, decodes corner_id ("P500_-200") to approximate XYZ

**Prompt summary:** `summarise_enriched_issues_for_prompt(enriched_issues) -> str`
- Groups by (segment_display_name, issue_type), counts unique lap numbers
- Unresolved section: explicitly instructs AI "do not invent corner names"

**`DrivingAdvisor` wiring:**
- `_get_enriched_issue_context(laps) -> str` — reads config IDs; runs enrichment; returns summary; never raises
- `_build_coaching_prompt`, `_build_setup_prompt`, `_build_combined_prompt` — enriched block takes precedence over `corner_issues_summary` when non-empty

**Deferred:**
- Live current-segment lookup → **implemented in Group 17J**
- PTT marker capture
- Track auto-detection from telemetry
- Graphical split/merge editing

**Test coverage:** 76 tests in `tests/test_group17i_track_issue_enrichment.py` — 15 test classes

---

## Group 17J — Live Current Segment Resolver

**New module:** `data/live_segment_resolver.py` — pure Python, no PyQt6

**Purpose:** Map a real-time telemetry packet position to the best matching reviewed track segment for live engineer display, voice position announcements, and live coaching context.

**Core function:** `resolve_live_segment(loc_id, lay_id, position, base_dir, config) -> LiveSegmentResolverResult`
- Resolves reviewed track model via `resolve_best_track_model()` (Group 17G)
- Loads reference path for XYZ→lap_progress conversion
- Matching priority: segment_id exact → lap_progress range → distance_along_lap_m via ref path → XYZ nearest via ref path → nearest midpoint fallback → UNRESOLVED

**Enums:**
- `LiveSegmentResolutionConfidence`: HIGH / MEDIUM / LOW / UNKNOWN
- `LiveSegmentResolutionStatus`: matched / matched_nearest / no_reviewed_model / no_position_data / no_segment_bounds / error

**Dataclasses:**
- `LivePosition`: lap_progress, pos_x/y/z, distance_along_lap_m, segment_id, speed_kph
- `LiveSegmentMatch`: full match result with prev/next segment, confidence, source, warnings
- `LiveSegmentResolverResult`: status, match, model_source, warnings, errors
- `LiveSegmentResolverConfig`: include_needs_more_laps, include_unreviewed, allow_not_ai_ready, max_xyz_match_distance_m

**GT7 packet limitations (documented, not worked around):**
- No native lap_progress field — `packet_to_live_position()` never invents lap_progress
- `road_distance` (per-lap, resets at S/F) is stored in `LivePosition.road_distance_m` but NOT converted to `distance_along_lap_m` by the packet adapter — requires a `LapStartOffsetCalibration` (Group 17L)
- XYZ matching via reference path is the primary position method when no calibration is available

**Adapters:**
- `packet_to_live_position(packet) -> Optional[LivePosition]` — duck-typed GT7 packet → LivePosition; guards paused/loading/off-track/zero-xyz; never raises
- `format_live_segment_for_engineer(result) -> str` — compact one-line wording, no invented corner names
- `get_live_segment_context_for_prompt(loc, lay, position, base_dir) -> str` — full prompt block for AI injection; returns "" on NO_REVIEWED_MODEL

**`DrivingAdvisor` wiring:**
- `_get_live_segment_context(live_position=None) -> str` — resolves live segment; returns "" if no position or no IDs; never raises
- `_build_coaching_prompt`, `_build_setup_prompt`, `_build_combined_prompt` — accept optional `live_position` kwarg; live segment block injected after track intel block when non-empty

**Deferred:**
- Voice position announcements ("entering T1 Braking Zone")
- Track auto-detection from telemetry
- Graphical split/merge editing

**Test coverage:** 78 tests in `tests/test_group17j_live_segment_resolver.py` — 17 test classes

---

## Group 17K — Segment-Aware Live Coaching Rules

**New module:** `data/live_segment_coaching.py` — pure Python, no PyQt6

**Purpose:** Convert a live segment match + enriched issue history into a single deterministic, anti-spam driving cue for real-time display or voice delivery. All decisions are deterministic — same inputs produce same output.

**Enums:**
- `LiveCoachingCueType` (13): braking_stability, brake_release, rotation, throttle_pickup, exit_drive, gear_choice, short_shift, limiter_warning, fuel_save, kerb_caution, tyre_management, track_limits, no_call
- `LiveCoachingPriority` (4): low, medium, high, urgent
- `LiveCoachingSuppressionReason` (12): no_segment, low_confidence, unreviewed_model, low_issue_confidence, unresolved_issue, rejected_segment, needs_more_laps, seed_only, cooldown, max_cues_reached, no_matching_rule, disabled

**Dataclasses:**
- `LiveCoachingCue` — cue_type, priority, text, basis_segment_id/display_name/type, basis_issue_type, issue_repetition_count, match_confidence, created_at_lap/progress
- `LiveCoachingDecision` — suppressed, cue (Optional), suppression_reason, all_candidates, debug_info
- `LiveCoachingConfig` — enable_fuel_save_cues (default False), enable_kerb_cues (True), enable_tyre_management_cues (False), min_progress_delta_between_same_segment_cue (0.10), suppress_same_cue_for_laps (3), max_cues_per_lap (3), min_issue_repetitions (2), suppress_on_low_confidence (True), suppress_on_needs_more_laps (True)

**Cue template table:** 25 entries covering (issue_type × segment_type) pairs. Each entry: `(issue_type_str, segment_type_str_or_None, LiveCoachingCueType, LiveCoachingPriority, text_template)`. `{segment}` in template substituted with `display_name` when confidence is MEDIUM+; gracefully removed when name unavailable. Exact match first, `None` (any-segment) fallback second.

**`build_live_coaching_decision()` gate sequence:**
1. Segment unresolved (status ≠ MATCHED/MATCHED_NEAREST) → suppress NO_SEGMENT
2. model_source == seed_only → suppress SEED_ONLY
3. Segment warnings contain "rejected" → suppress REJECTED_SEGMENT
4. Segment warnings contain "needs more calibration" → suppress NEEDS_MORE_LAPS (if config flag set)
5. Confidence LOW/UNKNOWN → suppress LOW_CONFIDENCE (if config flag set)
6. No enriched issues at this segment → suppress NO_MATCHING_RULE
7. Build candidates: filter issues by segment_id (exact) or segment_type (fallback), group by issue_type, skip if < min_issue_repetitions, gate fuel_save/tyre_management on config flags, look up template, downgrade priority if confidence==low
8. No candidates → suppress NO_MATCHING_RULE
9. Sort candidates by priority desc; pick best
10. Cooldown check: same cue_type + segment_id within suppress_same_cue_for_laps laps or within min_progress_delta → suppress COOLDOWN
11. max_cues_per_lap check → suppress MAX_CUES_REACHED
12. Return active cue

**Helpers:**
- `format_live_coaching_for_prompt(decision) -> str` — returns "" when suppressed; returns `## Live Coaching Cue\n<text>\nBasis: <issue + segment + laps + confidence>.` when cue fires
- `get_live_coaching_debug_metadata(decision) -> dict` — 4 fields: live_coaching_cue_included, live_coaching_cue_type, live_coaching_priority, live_coaching_basis_segment, live_coaching_suppression_reason

**No invented corner names:** cue text uses `display_name` only when segment confidence ≥ MEDIUM. When name unavailable, `{segment}` reference is stripped gracefully — text never reads "{segment}" literally.

**`DrivingAdvisor` wiring:**
- `_get_live_coaching_context(live_position=None, laps=None) -> str` — resolves live segment, builds enriched issues from laps, calls `build_live_coaching_decision()`, returns `format_live_coaching_for_prompt()`
- `_build_coaching_prompt` — `live_coaching_block` injected in `extra_sections` after `live_segment_block`

**Design boundaries (deferred):**
- Text-to-speech / voice announcement integration
- Real-time track auto-detection
- PTT marker capture
- Multi-cue display (config.allow_multi_cue=False by default)
- Tyre management cues (opt-in, default disabled — too noisy)
- Fuel-save cues (opt-in, default disabled — requires strategy context)

**Test coverage:** 78 tests in `tests/test_group17k_live_segment_coaching.py` — 19 test classes

---

## Group 17L — Lap-Start Offset Calibration and Road-Distance Mapping

**New module:** `data/lap_distance_mapper.py` — pure Python, no PyQt6

**Problem solved:** GT7's `road_distance` resets to ~0.0 at the start/finish line each lap and increases to ~track_length_m. Our reference path's `distance_along_lap_m` starts from 0 at wherever the calibration lap began. If both start at the same point (S/F line), offset = 0. If calibration started elsewhere (e.g. pit exit), an offset converts between the two.

**Formula:** `model_distance = normalise_distance(road_distance - offset_m, track_length_m)`

**`LapStartOffsetCalibration`** stored as `<loc>__<lay>__lap_offset.json` in `data/track_models/`.

**`live_segment_resolver.py` changes:**
- `LivePosition.road_distance_m` — raw GT7 field, populated by `packet_to_live_position()`
- `enrich_position_with_road_distance(position, calibration)` — standalone converter
- `resolve_live_segment(…, offset_calibration=None)` — Priority 3 now maps road_distance before XYZ

**Updated matching priority:** segment_id → lap_progress → **road_distance+offset** → distance_along_lap_m → XYZ nearest → nearest midpoint → unresolved

**Confidence handling:** road_distance match inherits model base confidence; downgraded one level when calibration confidence is LOW or UNKNOWN.

---

## Group 17M — Runtime UAT and Calibration Workflow Hardening

**New module:** `data/track_modelling_runtime_check.py` — pure Python pipeline status aggregator

**Problem solved:** No single runtime view of whether the full pipeline (track selected → packets → recording → build → segments → resolver → offset → live segment) is healthy or blocked.

**`RuntimeCheckResult`** dataclass — 14 fields (has_track, resolver_source, resolver_ai_ready, offset_status, offset_m, has_road_distance, live_segment_id, live_resolution_status, warnings, errors); `summary_text()` → compact multi-line string for UI display.

**`run_track_modelling_runtime_check()`** — never raises; duck-typed; aggregates all four pipeline stages (resolver / offset / live position / live segment).

**`ui/track_modelling_vm.py` additions:**
- `get_workflow_error_message(key)` — maps 11 error keys to human-readable UI strings (safe for unknown keys)
- `get_calibration_button_states(ctrl_state, has_track, has_completed_laps, has_ref_path, has_review_model, selected_segment_id, has_track_length)` — pure-Python button state helper; 15-key dict; covers all 5 controller states + offset workflow buttons
- `format_calibration_status_extended(status_summary, last_packet_age_s)` — packet age (green/amber/red), sample count, lap count, path info, saved path
- `format_lap_offset_status(offset_calibration, track_length_m)` — provisional/validated status, offset_m, confidence, source, warnings, provisional_note
- `format_live_resolver_status_summary(loc_id, lay_id, resolver_result, offset_calibration, live_position, live_segment_result)` — newline-separated multi-line status string

**`ui/dashboard.py` additions (Group 17M):**
- `_tm_lbl_packet_age` — packet age label with colour feedback; updated on every calibration packet
- `_tm_last_packet_time` — wall-clock float for age computation
- `_tm_offset_calibration` — holds `LapStartOffsetCalibration` or None
- Lap Offset Calibration QGroupBox — Create Zero Offset / Load Offset / Save Offset buttons; provisional warning note; status/detail/warning labels
- `_tm_get_track_length_m()` — derives from reference path points[-1] or seed layout.length_m
- `_tm_update_packet_age_label()`, `_tm_update_offset_status()`, `_tm_create_zero_offset()`, `_tm_load_offset()`, `_tm_save_offset()`

**`data/lap_distance_mapper.py` change:**
- `create_offset_zero()` default source is now `"zero_offset"` (was `"manual"`); raises `ValueError` on non-positive track_length_m

**New doc:** `docs/TRACK_MODELLING_RUNTIME_UAT.md` — 15-section manual UAT checklist (track selection, GT7 connection, recording, lap count, build/save, segment detection, review, offset calibration, resolver status, live segment resolution, error states)

**Button state rules** (definitive list for future reference):
- `start`: has_track AND ctrl_state in (inactive, stopped, built, error)
- `stop`: ctrl_state == recording
- `build`: ctrl_state in (stopped, built) AND has_completed_laps
- `save_path`, `detect_segments`: has_ref_path
- `confirm`, `rename`, `reject`, `needs_more_laps`, `split_required`, `merge_required`: has_review_model AND selected_segment_id is not None
- `save_review`: has_review_model
- `create_zero_offset`: has_track AND has_track_length
- `load_offset`: has_track
- `save_offset`: has_offset (offset_calibration is not None)

**Provisional vs validated** (for offset calibration):
- Provisional: `calibration_source == "zero_offset"` OR confidence in (low, unknown)
- Validated: confidence in (high, medium) AND source != "zero_offset"

---

---

## Group 17R — Seed Map Overlay, True Map Alignment, and Recalibration Workflow

### Problem Solved

Six runtime defects observed during Daytona Road Course UAT after Group 17Q was implemented:

| Defect | Description |
|--------|-------------|
| DEF-17R-001 | Corner labels showed T1–T12 but were strongest curvature peaks, not positionally verified |
| DEF-17R-002 | `TrackMapDrawData.seed_overlay_note` was never set at runtime |
| DEF-17R-003 | Alignment panel had no explicit "Seed truth source" row |
| DEF-17R-004 | Old "Corner count mismatch" warnings from `detect_track_segments()` leaked into Segment Diagnostics |
| DEF-17R-005 | Rebuild/Recalibrate button was a silent no-op (only cleared the accepted flag) |
| DEF-17R-006 | Lap offset calibration statuses not explained in the UI |

### Changes

**`ui/track_model_alignment_vm.py`:**
- `format_alignment_summary()` returns new `"seed_truth_source"` key:
  - `"Metadata only — no coordinate or window data"` when `seed_corner_positions_available=False`
  - `"Seed corner windows (N defs)"` when positions are available
- `seed_position_status` text updated from "Unavailable — count only" to "Unavailable — corner labels are curvature peaks, not verified positions"

**`ui/track_map_vm.py`:**
- `build_track_map_draw_data()` sets `seed_overlay_note` based on `station_map.seed_corner_positions_available`:
  - If `False`: *"Seed centreline not available — showing telemetry-derived model only. Corner labels are curvature peaks, not verified seed positions."*
  - If `True`: `""` (no note needed)
- `project_to_screen()` now passes `seed_overlay_note` through to the projected `TrackMapDrawData`

**`ui/dashboard.py`:**
- New "Seed truth source" row in the Track Model Alignment panel (`_tm_al_seed_truth_source`)
- `_tm_refresh_alignment_panel()` wires the new label
- `_tm_rebuild_model()` rewritten to actually clear the station map:
  - Sets `self._tm_station_map = None` and `self._tm_alignment_result = None`
  - Pushes empty draw data to both map widgets
  - Resets alignment panel to "Not built"
  - Shows dialog: *"Station map cleared. Start Calibration and drive clean laps to rebuild the track model."*
- Rebuild button tooltip updated to explain what it does
- `_tm_detect_segments_safe()` suppresses "Corner count mismatch" and "corners vs expected" warnings when a station map with seeded corners is authoritative (DEF-17R-004)
- Lap Offset Calibration `_off_note` updated to explain the three status states: Not loaded / Zero offset provisional / Calibrated

### Key Runtime Behaviour

When Daytona's seed YAML has no `corners:` entries (the current state):
- `seed_corner_positions_available = False`
- The alignment panel shows: Seed truth source = "Metadata only — no coordinate or window data"
- Seed corner positions = "Unavailable — corner labels are curvature peaks, not verified positions"
- Match status is capped at GOOD_MATCH (ACCEPTABLE_MATCH is still blocked without seed windows)
- The station map's `seed_overlay_note` is populated so the map widget can display a note
- "Corner count mismatch" warnings from `detect_track_segments()` are suppressed because the station map owns corner geometry

To unlock ACCEPTABLE_MATCH and the Accept button, the Daytona seed YAML needs `corners:` entries with `apex_progress_pct`, `start_progress_pct`, and `end_progress_pct` for each of T1–T12.

### Test Coverage

`tests/test_group17r_seed_overlay_alignment.py` — 38 tests:
- DEF-17R-002: `seed_overlay_note` set when positions unavailable; empty when available; preserved by `project_to_screen()`
- DEF-17R-003: `seed_truth_source` key present in `format_alignment_summary()`, correct values for both cases
- DEF-17R-001: `seed_position_status` mentions curvature peaks when unavailable; matched count when available
- DEF-17R-004: filtering logic for "Corner count mismatch" / "corners vs expected" warning patterns
- DEF-17R-005: `format_alignment_summary(None)` → "Not built"; `get_acceptance_button_states()` with no map
- DEF-17R-006: `format_lap_offset_status()` status labels for not-loaded, zero offset, calibrated
- Structural: `TrackMapDrawData.seed_overlay_note` field exists and defaults to `""`

---

## Next Steps

1. Voice position announcements using live segment resolver
2. Live coaching voice delivery using LiveCoachingCue
3. Graphical split/merge editing UI
4. Wire `layout_id` from Event Planner (if event track can be safely resolved to seed ID)
5. Populate Daytona corner windows in seed YAML to unlock ACCEPTABLE_MATCH (requires driving measurements)

---

## Group 17O — Seeded 1m Track Map, Width Corridor, Map Matching, Visual Verification

### Problem Solved

Group 17E segment detection used telemetry behaviour (speed minima, brake, throttle, gear, RPM) to classify track anatomy. This produced non-geometry items — limiter approaches, kerb candidates, gear zones, fuel-saving candidates — instead of true geometric boundaries. The Daytona Road Course run showed only 5 corners instead of the expected 12.

### Three-Layer Architecture

| Layer | Content | Source | Changes Per Car? |
|-------|---------|--------|------------------|
| 1 — Track Model | Corner positions, curvature, gradient, width corridor | X/Y/Z geometry from reference path | No |
| 2 — Driver Reference Path | Driving line | Calibrated TelemetrySample path | Yes (car-specific) |
| 3 — Telemetry Overlay | Lock-ups, oversteer, gear zones | Behaviour events attached to stations | Yes (session-specific) |

### 1m Station Map (`data/track_station_map.py`)

- `resample_path_to_uniform_spacing(xyz_points, spacing_m=1.0)` — arc-length resampling with linear interpolation
- `_compute_heading()` — atan2(dx, dz) in XZ plane; `_compute_curvature()` — heading change per metre + rolling average (window=15)
- `_find_curvature_peaks()` — iterative peak suppression with `min_separation_m=80 m`
- `_detect_corners()` — if detected < expected, placeholders fill the largest gaps and are renumbered T1..Tn
- `_assign_corner_phases()` — BRAKING (–240 to –140 m), TURN_IN (–140 to –40 m), APEX (±40 m), EXIT (+40 to +140 m)
- Daytona invariant: always produces exactly 12 seeded corners regardless of curvature detection count

### Map Matching (`data/track_map_matching.py`)

- `find_nearest_station_idx(x, z, stations)` — linear scan on XZ distance
- `_lateral_offset(px, pz, sx, sz, heading)` — dot product with left perpendicular (cos θ, –sin θ)
- `match_position_to_map(x, y, z, station_map, speed_kph)` — confidence: HIGH ≤5 m, MEDIUM ≤20 m, LOW ≤60 m, UNKNOWN >60 m
- Pit/out-lap detection: speed <8 kph OR dist >60 m → `is_pit_likely=True`
- `is_likely_outlap(station_m, lap_length_m, has_crossed_start_finish)` → True if no S/F crossing yet

### Width Corridor (`data/track_width_model.py`)

- Seed default: 12 m applied to all stations initially
- `collect_lateral_offsets()` — accumulates per-station lateral offsets from USABLE calibration laps
- `build_width_estimates()` — requires ≥2 laps; observed envelope always ≤ seed width
- `apply_width_estimates_to_map()` — in-place update of station widths
- Helpers: `is_near_left/right_edge()`, `unused_track_width_pct()`

### Drawing Primitives (`ui/track_map_vm.py` — no PyQt6)

- `TrackMapDrawData`: centreline, width_left/right, start_finish, corner_labels, car_dot, telemetry_trace, bounds, status_text, confidence_color
- `build_track_map_draw_data(station_map, match_result, telemetry_trace)` — world-space XZ primitives; car dot placed at `station.x + lateral*cos(heading), station.z - lateral*sin(heading)`
- `project_to_screen(draw_data, canvas_w, canvas_h, margin=20)` — uniform scale + Y-axis reflection

### Dashboard Integration (`ui/dashboard.py`)

- `TrackMapWidget(QWidget)` — QPainter canvas class; renders TrackMapDrawData using QPainter
- Track Modelling tab: "Station Map" group box with map widget (min 300 px height) after Calibration Session group
- Live tab: track map widget replaces logo in mid_row; live car dot updates on every calibration packet
- `_tm_try_build_station_map()` — automatically called after successful Build Reference Path
- `_tm_update_live_map_dot(packet)` — extracts XYZ from packet, calls `match_position_to_map()`, refreshes both widgets

### Tests (76 across 14 categories, all pass)

File: `tests/test_group17o_track_station_map.py`

Categories: station model build, resampling, nearest station, station_m/progress_pct, lateral offset, edge distances, missing width, pit/out-lap, Daytona 12-corner guarantee, telemetry overlay separation, drawing primitives (no PyQt), car dot, low-confidence state, legacy 200-point path handling

---

## Group 17O UAT Remediation — Runtime Integration Fixes (2026-06-25)

### DEF-17O-UAT-001: Wrong controller attribute

The station map builder read `ctrl._ref_path` — a non-existent attribute. The reference path is stored at `ctrl._last_build_result.reference_path`. Fixed by changing `_tm_try_build_station_map()` to read the correct attribute chain. Method now also accepts an explicit `ref_path` argument so the disk-load path in `_tm_detect_segments_safe()` can pass a loaded `ReferencePath` directly.

### DEF-17O-UAT-002: Telemetry overlays in Segment Review

**Round 1 fix:** Added `_TELEMETRY_OVERLAY_SEG_TYPES` frozenset. After `_create_seg_review()`, overlay segments are filtered from `review.segments` so they never reach the table.

**Round 2 update (DEF-17O-UAT-006):** BRAKING_ZONE and TRACTION_ZONE reclassified as overlays. Both are generated by the corner detection loop with `calibration_car_id` set and explicit Porsche RSR warnings. They are car-specific behaviour, not universal track geometry.

**Current classification:**

Geometry types (in Segment Review): STRAIGHT, CORNER_ENTRY, APEX_ZONE, CORNER_EXIT, START_FINISH.

Telemetry overlay types (excluded from Segment Review): GEAR_ZONE, LIMITER_ZONE, FUEL_SAVING_CANDIDATE, KERB_OR_BUMP_CANDIDATE, BRAKING_ZONE, TRACTION_ZONE.

### DEF-17O-UAT-003: Old detection count overriding station map count

The station map guarantees `corners_expected` (e.g. 12 for Daytona) via placeholder filling. The old Group 17E detection may find fewer curvature peaks (e.g. 5). The fix: when `_tm_station_map` is available, `_tm_detect_segments_safe()` uses station map corner counts for the "Expected corners" label instead of the old detection count. The label now reads:
`"{n_seeded} seeded corners | {n_detected_geo} curvature-detected | {n_placeholder} estimated"`

This preserves the Group 17O architecture guarantee: the 17O station map is the geometric ground truth; Group 17E detection is a supplementary telemetry overlay source.

## Group 17O UAT Remediation Round 2 — Critical Seed Lookup Fix (2026-06-25)

### DEF-17O-UAT-005/007: TrackSeedLoadResult has no `.layouts` attribute (CRITICAL)

`_tm_try_build_station_map()` contained:
```python
for layout in self._tm_seed_result.layouts:  # AttributeError!
```

`TrackSeedLoadResult` has `.track_locations: list[TrackLocationSeed]`, where each `TrackLocationSeed` has `.layouts: list[TrackLayoutSeed]`. There is NO top-level `.layouts` attribute. This `AttributeError` was silently caught by `except Exception`, causing:
- Station map never built (map showed "No track map loaded")
- `corners_expected` always 0 (no placeholder filling → only 5 curvature corners)
- Both DEF-17O-UAT-005 and DEF-17O-UAT-007 were the same root cause

**Fix:** `get_selected_layout(self._tm_seed_result, loc_id, lay_id)` already imported from `ui.track_modelling_vm`. This helper navigates `seed_result.track_locations` → `loc.layouts` correctly.

Also reads `loc_id = self._tm_location_combo.currentData()` (was missing — only `lay_id` was read).

### DEF-17O-UAT-008: Station map persistence

- After each successful build, `_export_station_map(self._tm_station_map)` saves to `data/track_models/<loc>__<lay>__station_map.json` (best-effort).
- `_tm_try_load_station_map_from_disk(loc_id, lay_id)` added: uses `_find_station_map_path()`, loads JSON if found, updates both map widgets.
- Called from `_tm_on_layout_changed()` so saved maps appear immediately on layout selection.

### DEF-17O-UAT-004: Build info label shows station map count

After building station map, `_tm_lbl_build_info` is updated to:
`"Path: N pts | Conf: X | Map: N stations / N corners"`

### Turn column in Segment Review

`_tm_refresh_seg_table()` matches each segment's `lap_progress_mid` to the nearest `SeededCorner` in `_tm_station_map.seeded_corners`. If the nearest corner is within 15% lap progress, its `corner_id` (e.g. "T3") is used for the Turn column — even for non-apex segments (braking, entry, exit) whose `turn_number` field is `None`.

---

## Group 17P — Seed-to-Telemetry Track Model Alignment and Whole-Model Acceptance (2026-06-25)

### Root cause: `_detect_corners()` had no upper cap at corners_expected

Before Group 17P, `_detect_corners()` would:
1. Find ALL peaks above threshold (potentially 36 for Daytona)
2. Check `if len(detected_indices) < corners_expected` — only RELAXED the threshold, never TRIMMED
3. Return all 36 peaks as official `SeededCorner` objects T1-T36

**Fix:** When `len(detected_indices) > corners_expected`, sort by curvature magnitude, take top N, store excess in `extra_indices`. `_detect_corners()` now returns `(official_corners: List[SeededCorner], extra_peaks: List[SeededCorner])`.

### New fields and modules

**`data/track_station_map.py`:**
- `TrackStationMap.extra_curvature_peaks: List[SeededCorner]` — peaks XP1..XPn, never in `seeded_corners`
- `_detect_corners()` return changed to tuple `(official, extras)`
- `build_track_station_map()` unpacks: `corners, extra_peaks = _detect_corners(...)`
- JSON export/import includes `extra_curvature_peaks` list

**`data/track_model_alignment.py` (NEW):**
- `TrackModelMatchStatus` enum: NOT_READY / FAILED_MATCH / PARTIAL_MATCH / GOOD_MATCH / ACCEPTABLE_MATCH
- `CornerAlignmentResult`: corner_id, approx_progress, is_placeholder, confidence
- `SectorAlignmentResult`: seed_sector_count, status, note
- `TrackModelAlignmentResult`: full alignment result with blockers/warnings/accepted/accepted_at
- `align_track_model(station_map, layout_seed)` — pure function, no side effects
- `export/import/find_accepted_model_json()` for persistence to `data/track_models/<loc>__<lay>.accepted_model.json`

**`ui/track_model_alignment_vm.py` (NEW):**
- `format_alignment_summary(result)` — 17-key dict for all panel labels
- `get_acceptance_button_states(result, has_station_map)` — {"accept": bool, "rebuild": bool}
- `format_mismatch_reasons(result)` — list of "BLOCKER: ..." / "Warning: ..." strings
- `manual_approval_buttons_enabled(in_alignment_workflow=True)` — always False (per-segment approval removed)

**`ui/track_map_vm.py`:**
- `TrackMapDrawData.seed_overlay_note: str` — shown in panel when seed centreline is not available

### Acceptance button criteria (STRICT)

Accept Track Model button is enabled ONLY when:
1. `match_status == ACCEPTABLE_MATCH` (lap delta < 2%, no blockers)
2. `result.blockers == []`
3. `result.accepted == False` (re-disables once accepted; Rebuild clears it)

### Workflow state machine

| State | Condition |
|-------|-----------|
| "Not built" | No station map, or match_status == NOT_READY |
| "Built — alignment pending" | Station map exists but FAILED_MATCH or PARTIAL_MATCH |
| "Aligned — not accepted" | GOOD_MATCH or ACCEPTABLE_MATCH, accepted=False |
| "Accepted and saved" | accepted=True |

### Sector alignment caveat

GT7 seed data provides a sector COUNT but no sector boundary positions (progress values). Sector alignment status is always "not_available" with a note: "non-critical — sector count noted but cannot be verified against the model." This is correct and expected behaviour — it is not a defect.

---

## Group 17Q — Seed Corner Position Matching and Acceptance Integrity (2026-06-26)

### Root cause: Group 17P capped by count, not by position

Group 17P fixed Daytona reporting T1–T36 by capping at `corners_expected=12`. But the cap selected the 12 strongest curvature peaks, which might be at the wrong positions — not necessarily Daytona's actual T1–T12. ACCEPTABLE_MATCH was reachable with the correct count but wrong corners.

### New module: `data/seed_corner_matching.py`

Pure computation module — no project imports (no circular dependency risk). Imported lazily inside `build_track_station_map()`.

**`CornerMatchStatus(str, Enum)` — 6 values:**

| Value | Meaning |
|-------|---------|
| `MATCHED` | Peak found in seed window, confirmed |
| `MULTIPLE_CANDIDATES` | Multiple peaks in window; strongest selected (extras become XP) |
| `NO_CANDIDATE_IN_WINDOW` | Window had no curvature peaks → placeholder was used |
| `SEED_POSITION_UNAVAILABLE` | Seed has no per-corner window data |
| `PLACEHOLDER_USED` | Corner is a placeholder (consistent with `is_seeded_placeholder`) |
| `EXTRA_PEAK_SUPPRESSED` | Peak fell outside all windows — recorded as XP diagnostic |

**`CornerCandidateMatch` dataclass:**

| Field | Type | Purpose |
|-------|------|---------|
| `seed_corner_id` | `str` | Which seed corner this match describes |
| `matched_candidate_id` | `str` | Peak index used (or "" for placeholder) |
| `candidate_progress_pct` | `float` | Actual detected apex progress |
| `expected_apex_progress_pct` | `float` | Seed apex_progress_pct |
| `delta_pct` | `float` | `abs(candidate - expected)` |
| `match_status` | `CornerMatchStatus` | One of the 6 values above |
| `confidence` | `float` | Curvature magnitude of matched peak |
| `notes` | `str` | Human-readable detail |

**`match_peaks_to_seed_windows()` algorithm:**

1. Build a list of `(curvature, peak_idx, window_idx)` triples for every (peak, window) pair where `window_start <= peak_progress <= window_end`
2. Sort descending by curvature
3. Greedy: assign the first unassigned peak+window pair in order
4. Unassigned windows → `-1` (placeholder needed)
5. Unassigned peaks → `extra_indices` (XP diagnostics)
6. Returns: `official_indices`, `extra_indices`, `corner_matches`

### New dataclass: `SeedCornerDefinition` (in `data/track_intelligence.py`)

```python
@dataclass
class SeedCornerDefinition:
    corner_id:          str
    display_name:       str   = ""
    apex_progress_pct:  float = 0.0
    start_progress_pct: float = 0.0
    end_progress_pct:   float = 0.0
    direction:          Optional[str] = None
    sector_id:          Optional[int] = None
    source:             str   = "seed"
    confidence:         str   = "medium"
```

`TrackLayoutSeed.corner_definitions: list[SeedCornerDefinition]` added with `field(default_factory=list)`. Backward compatible — existing YAML seeds without `corners:` key load with empty list. YAML schema: each entry under `corners:` has `id`, `display_name`, `apex_progress_pct`, `start_progress_pct`, `end_progress_pct` (all 0–100%).

### New `TrackStationMap` field

`seed_corner_positions_available: bool = False` — True when `build_track_station_map()` used window-based selection (i.e., layout_seed had `corner_definitions`). Persisted in station map JSON. Defaults to False when loading old files (backward compatible).

### `build_track_station_map()` branching

- **With corner defs (Group 17Q path):**
  1. Call `_find_curvature_peaks()` to get all peaks
  2. Build progress/curvature arrays
  3. Call `match_peaks_to_seed_windows()`
  4. Official corners: one per window, at peak position (or placeholder at apex_progress_pct if no peak)
  5. Extra peaks → `extra_curvature_peaks` list
  6. `seed_corner_positions_available = True`
- **Without corner defs (legacy path):**
  1. Call `_detect_corners()` → curvature cap at N strongest (Group 17P)
  2. `seed_corner_positions_available = False`

### `TrackModelAlignmentResult` — 4 new fields

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `seed_corner_positions_available` | `bool` | `False` | Propagated from station map |
| `corner_position_match` | `str` | `"NOT_AVAILABLE"` | "PASS" / "PARTIAL" / "FAIL" / "NOT_AVAILABLE" |
| `corners_matched` | `int` | `0` | Count of MATCHED windows |
| `corner_candidate_matches` | `List[CornerCandidateMatch]` | `[]` | Per-window result |

### Status logic in `align_track_model()`

| Scenario | Match status cap | `corner_position_match` |
|----------|-----------------|------------------------|
| No seed corner_defs | GOOD_MATCH (max) | NOT_AVAILABLE |
| All windows matched, lap delta < 2% | ACCEPTABLE_MATCH | PASS |
| Some windows matched | GOOD_MATCH / PARTIAL_MATCH | PARTIAL |
| Unmatched windows → blockers → | No better than PARTIAL | FAIL |

**CRITICAL:** `ACCEPTABLE_MATCH` is only reachable when `corner_defs` are present. Without corner defs, highest achievable status is `GOOD_MATCH`, which means **Accept Track Model button is always disabled** when the seed lacks per-corner window data.

### UI changes

**`ui/track_model_alignment_vm.py` — 4 new summary keys:**

| Key | Value when no defs | Value with defs |
|-----|-------------------|-----------------|
| `seed_position_status` | `"Unavailable — count only"` | `"Available (N/N matched)"` |
| `corners_matched` | `"N/A (no seed positions)"` | `"12 / 12"` |
| `corner_position_match` | `"Not available"` | `"Pass"` / `"Partial"` / `"Fail"` |
| `corner_position_color` | `"#888888"` | `"#88EE88"` / `"#F5A623"` / `"#EE4444"` |

**`ui/dashboard.py` — 3 new label rows in alignment panel:**
- Seed corner positions → `_tm_al_seed_position_status`
- Corners matched → `_tm_al_corners_matched`
- Corner pos match → `_tm_al_corner_position_match`

### Test coverage

29 tests in `tests/test_group17q_seed_corner_matching.py`:
- `TestDef17QMatchPeaksToSeedWindows` (8 tests): unit tests of the greedy algorithm
- `TestDef17QCorrectPeaksSelected` (3 tests): alignment uses seed windows, no T13+
- `TestDef17QSeedPositionUnavailable` (4 tests): honesty when seed lacks per-corner data
- `TestDef17QAcceptanceGate` (4 tests): accept requires seed position evidence
- `TestDef17QExtraPeaksDiagnostic` (2 tests): XP peaks never in official corners
- `TestDef17QUIPanelSummary` (6 tests): 4 new summary keys correct in all states
- `TestDef17QBackwardCompat` (2 tests): JSON round-trip for new fields, old JSON loads with defaults

---

## Group 17S — Seed Track Definition Authoring, Corner Complexes, True Alignment Gate

### New dataclasses

**`SeedSectorDefinition`** (in `data/track_intelligence.py`):
```python
@dataclass
class SeedSectorDefinition:
    sector_id:          str
    display_name:       str   = ""
    start_progress_pct: float = 0.0
    end_progress_pct:   float = 100.0
    source:             str   = "estimated"
    confidence:         str   = "low"
```

**`CornerComplexDefinition`**:
```python
@dataclass
class CornerComplexDefinition:
    complex_id:         str
    display_name:       str
    member_corner_ids:  list = field(default_factory=list)
    start_progress_pct: float = 0.0
    end_progress_pct:   float = 0.0
    sector_id:          Optional[str] = None
    coaching_name:      str   = ""
    notes:              str   = ""
    source:             str   = "estimated"
    confidence:         str   = "low"
```

**`SeedAuditResult`**:
```python
@dataclass
class SeedAuditResult:
    has_metadata, has_lap_length, has_sector_definitions,
    has_corner_windows, has_corner_complexes, has_seed_centreline: bool
    corner_count, sector_count, complex_count, centreline_point_count: int
    max_match_status: str     # "GOOD_MATCH" or "ACCEPTABLE_MATCH"
    missing_for_full_accept: list[str]
```

### TrackLayoutSeed additions

```python
sector_definitions: list[SeedSectorDefinition] = field(default_factory=list)
corner_complexes: list[CornerComplexDefinition] = field(default_factory=list)
```

### New YAML schema fields

Both parsed by `_parse_layout()` via new helpers `_parse_sector_def()` and `_parse_complex_def()`.

```yaml
sector_definitions:
  - sector_id: S1
    display_name: "Sector 1"
    start_progress_pct: 0.0
    end_progress_pct: 33.0
    source: estimated
    confidence: low
corner_complexes:
  - complex_id: "T10T11"
    display_name: "T10/T11 Complex"
    member_corner_ids: ["T10", "T11"]
    start_progress_pct: 73.0
    end_progress_pct: 85.5
    sector_id: S3
    coaching_name: "Horseshoe"
    notes: "..."
    source: estimated
    confidence: low
```

### Daytona Road Course enriched data

`docs/track_modelling_seed/track_modelling_seed.yaml` now includes for Daytona Road Course:
- **12 corner windows** (T1–T12): T1 apex at 8.2% confirmed from UAT, T2–T12 estimated
- **3 sector definitions** (S1: 0–33%, S2: 33–66%, S3: 66–100%)
- **2 corner complexes**: BusStop (T1+T2) and T10T11 (T10+T11, coaching: "Horseshoe")

All source: "estimated", confidence: "low". Must be validated against GT7 telemetry before engineer_grade status.

### audit_layout_seed()

```python
def audit_layout_seed(layout_seed) -> SeedAuditResult:
    """Returns SeedAuditResult for any layout_seed (duck-typed) or None."""
```

- `has_seed_centreline` is always False — coordinate centreline not yet implemented
- `max_match_status = "ACCEPTABLE_MATCH"` when `has_corner_windows` is True; `"GOOD_MATCH"` otherwise
- Called from `format_alignment_summary(result, layout_seed)` to populate `seed_audit` key

### format_alignment_summary() change

Now accepts optional `layout_seed=None` second parameter. Returns `"seed_audit"` key in addition to all Group 17R keys. `"seed_audit"` is always `"—"` when result is None.

Example output: `"lap length, 3 sectors, 12 corner windows, 2 complexes, no centreline"`

### Turn assignment fix (DEF-17S-004)

`_tm_refresh_seg_table()` in `ui/dashboard.py` now:
1. Resolves `corner_definitions` from the selected layout's `TrackLayoutSeed`
2. For each segment, checks if `seg.lap_progress_mid` falls inside any corner window
3. If yes, assigns that corner's `corner_id` (window-based, not proximity-based)
4. Falls back to nearest-station-map-corner (±15%) only when no seed windows are available

Before: Straight at 0–7.3% (midpoint 3.65%) was assigned "T2" by proximity.
After: Straight at 0–7.3% gets no assignment (outside all windows). T1 window starts at 5.5%.

### Lap delta blocker change (DEF-17S-003)

In `data/track_model_alignment.py`:
- `delta_pct > _MAX_LAP_DELTA_GOOD_PCT (5%)` now adds to `blockers` (not `warnings`)
- Includes explanation of possible causes
- `delta_pct > _MAX_LAP_DELTA_PARTIAL_PCT (20%)` continues to produce "critical" blocker

Daytona 5.1% delta will now block acceptance with an explicit blocker message.

### Test coverage

36 tests in `tests/test_group17s_seed_definition_authoring.py` covering:
- Metadata-only seed audit (no corner windows, max status = GOOD_MATCH)
- Daytona loads with 12 corners, 3 sectors, 2 complexes
- T10/T11 are in a complex together; BusStop contains T1+T2
- Lap delta 5.1% creates a blocker; >20% creates critical; <5% no lap blocker
- Straight at 3% not assigned to T2; segment at 8.2% assigned T1
- format_seed_audit_summary display strings
- audit_layout_seed(None) returns has_metadata=False
- format_alignment_summary None and non-None include seed_audit key
- Backward compat: all existing layouts without new fields still load with empty lists

---

## Group 17T — Seed Coordinate Map Import and Full-Lap Alignment

### Objective

Add a second seed layer — `SeedCoordinateMap` — which stores actual XY (or XYZ) coordinates for each track station. Enable geometric comparison between the modelled station map (telemetry-derived, 1 m spacing) and this seed coordinate map. Block 100% geometry acceptance when the coordinate map is absent or shows >5% lap delta.

### New data layer: SeedCoordinateMap (Layer 1.5)

Located in `data/track_seed_coordinate_map.py`. JSON file at:

```
data/track_seed_maps/<track_location_id>__<layout_id>.seed_map.json
```

Schema identifier: `seed_coordinate_map_v1`.

```python
@dataclass
class SeedMapStation:
    station_m:      float
    progress_pct:   float
    x:              float = 0.0
    y:              float = 0.0
    z:              float = 0.0
    width_left_m:   Optional[float] = None
    width_right_m:  Optional[float] = None
    corner_id:      Optional[str] = None
    sector_id:      Optional[str] = None

@dataclass
class SeedCoordinateMap:
    track_location_id:       str
    layout_id:               str
    source:                  str   = "unknown"
    confidence:              str   = "low"
    lap_length_m:            float = 0.0
    start_finish_station_m:  float = 0.0
    stations:                List[SeedMapStation] = field(default_factory=list)
    has_z_coordinates:       bool = False
    has_corner_markers:      bool = False
    has_sector_markers:      bool = False
    has_width_corridor:      bool = False
    notes:                   str  = ""
```

Key functions:

- `seed_coordinate_map_filename(track_location_id, layout_id) -> str` — canonical file name
- `find_seed_coordinate_map_path(track_location_id, layout_id, base_dir=None) -> Optional[Path]`
- `load_seed_coordinate_map(track_location_id, layout_id, base_dir=None) -> Optional[SeedCoordinateMap]`
- `export_seed_coordinate_map_json(seed_map, output_dir=None) -> Path`
- `import_seed_coordinate_map_json(path) -> Optional[SeedCoordinateMap]`
- `resample_seed_map(seed_map, spacing_m=1.0) -> SeedCoordinateMap`

### New geometry alignment module: track_map_geometry_alignment.py

Located in `data/track_map_geometry_alignment.py`. Contains the geometric alignment engine.

**Thresholds:**

```python
_LAP_DELTA_BLOCKER_PCT  = 5.0    # >5% lap delta → blocker regardless of coordinate match
_LAP_DELTA_CRITICAL_PCT = 20.0   # >20% → critical blocker
_COORD_ACCEPT_MEAN_M    = 15.0   # mean coord error < 15 m required for acceptance
_COORD_ACCEPT_MAX_M     = 50.0   # max coord error < 50 m required
_SCALE_WARN_THRESHOLD   = 0.05   # scale deviation >5% → warning
```

**Key dataclasses:**

```python
@dataclass
class MapMismatchRange:
    start_progress_pct: float
    end_progress_pct:   float
    estimated_missing_m: float
    description:        str

@dataclass
class CornerCoordinateMatch:
    corner_id:           str
    seed_progress_pct:   float
    model_progress_pct:  Optional[float] = None
    delta_progress_pct:  Optional[float] = None
    delta_m:             Optional[float] = None
    matched:             bool = False

@dataclass
class SectorCoordinateMatch:
    sector_id:              str
    seed_start_progress_pct: float
    seed_end_progress_pct:   float
    model_start_progress_pct: Optional[float] = None
    model_end_progress_pct:   Optional[float] = None
    matched:                 bool = False

@dataclass
class CoordinateTransform:
    translation_x: float = 0.0
    translation_y: float = 0.0
    rotation_rad:  float = 0.0
    scale:         float = 1.0
    quality:       float = 0.0
    axis_flip_y:   bool  = False
    source:        str   = "auto"

@dataclass
class TrackMapGeometryAlignmentResult:
    has_coordinate_comparison:  bool  = False
    seed_coordinate_map_available: bool = False
    lap_length_delta_m:         float = 0.0
    lap_length_delta_pct:       float = 0.0
    mean_coord_error_m:         Optional[float] = None
    max_coord_error_m:          Optional[float] = None
    start_finish_offset_m:      Optional[float] = None
    missing_section_ranges:     List[MapMismatchRange] = field(default_factory=list)
    corner_matches:             List[CornerCoordinateMatch] = field(default_factory=list)
    sector_matches:             List[SectorCoordinateMatch] = field(default_factory=list)
    coordinate_transform:       Optional[CoordinateTransform] = None
    blockers:                   List[str] = field(default_factory=list)
    warnings:                   List[str] = field(default_factory=list)
    seed_stations_count:        int = 0
    model_stations_count:       int = 0
```

**Main entry point:**

```python
def align_maps_geometry(
    station_map,
    seed_map=None,     # Optional[SeedCoordinateMap]
    seed_layout=None,  # Optional[TrackLayoutSeed]
) -> TrackMapGeometryAlignmentResult
```

Behaviour:
- If `seed_map is None` and `seed_layout is None`: returns empty result (no lap delta available)
- If `seed_map is None` but `seed_layout` has `length_m`: computes lap delta, adds warning "Geometry match cannot be verified — coordinate map unavailable", adds blocker if delta > 5%
- If `seed_map` is provided: runs full coordinate comparison — transform estimation, mean/max error, missing section detection, corner matching, sector matching

**Coordinate transform algorithm:**

```
1. Centroid alignment → translation_x, translation_y
2. RMS radius ratio → scale
3. Coarse rotation scan: 0–359° in 15° steps, minimise mean nearest-neighbour error
4. Fine rotation: ±15° in 1° steps around best coarse angle
5. quality = 1 - (mean_error / rms_radius)
```

**Missing section detection:**

- Without coordinate data: if model lap < seed lap by > 5%, report missing range as "approx {model_end_pct:.0f}% – 100.0% (near lap boundary)"
- With coordinate data: scan consecutive inter-station distances; flag jumps > max(20 m, 10× expected_step); report midpoint of largest detected gap

### Changes to audit_layout_seed()

`audit_layout_seed()` in `data/track_intelligence.py` now accepts optional track/layout IDs:

```python
def audit_layout_seed(
    layout_seed,
    track_location_id: Optional[str] = None,
    layout_id_str:     Optional[str] = None,
) -> SeedAuditResult:
```

When both IDs are provided, calls `load_seed_coordinate_map()` to check for the JSON file. If found:
- `has_seed_centreline = True`
- `centreline_point_count = seed_map.station_count()`
- `missing_for_full_accept` updated with file path instruction

### Changes to TrackMapDrawData

`seed_centreline: List[MapPoint]` added as a defaulted field (value `[]`) to `TrackMapDrawData` in `ui/track_map_vm.py`. `build_track_map_draw_data()` now accepts `seed_coordinate_map=None` and populates `seed_centreline` from `SeedCoordinateMap.stations` (x, y). `project_to_screen()` projects `seed_centreline` alongside the telemetry centreline.

### Changes to format_alignment_summary()

New helper `format_geometry_alignment_summary(geo_result) -> str` in `ui/track_model_alignment_vm.py`. Returns:
- `"—"` when `geo_result is None`
- `"Seed coordinate map unavailable"` (or with length delta) when no coordinate comparison
- `"mean err {X:.1f} m, max {Y:.1f} m, length delta {Z:.1f}%[, N missing section(s)]"` when comparison ran

`format_alignment_summary()` gains optional `geo_result=None` third parameter and returns a `"geometry_match"` key.

### Changes to dashboard.py

- New "Geometry match" row in the alignment panel
- `_tm_refresh_alignment_panel()` loads `seed_coordinate_map` from disk (if track/layout IDs known) and passes to `align_maps_geometry()`
- `_tm_rebuild_model()` dialog now gives 4-step recalibration guidance including "Start Calibration mode before leaving pits" and "Drive 2–3 full clean laps crossing S/F line"

### Daytona status after Group 17T

No seed coordinate map file exists for Daytona. To enable full geometry match, create:

```
data/track_seed_maps/daytona_international_speedway__daytona_international_speedway__road_course.seed_map.json
```

with schema `seed_coordinate_map_v1` and GT7 XZ coordinate data derived from accepted telemetry runs.

### Test coverage

55 tests in `tests/test_group17t_seed_coordinate_map.py` covering:

- Missing seed coordinate map → `has_coordinate_comparison=False`, warnings include "unavailable"
- Seed coordinate map export/import round-trip preserves all fields
- `resample_seed_map` produces correct station count and interpolates midpoints
- Perfect circle vs identical circle → `mean_coord_error_m < 2.0`, no coordinate blockers
- 5.9% lap delta → blocker + `missing_section_ranges` populated
- Missing section description mentions progress percentages
- Rotated circle (45°) aligns after transform → `mean_err < 50 m`
- Translated circle aligns; translation vector approximately correct
- Scale mismatch (0.8×) → warnings include "scale"
- `model_stations_count` in result reflects full station map (not 200 points)
- `has_seed_centreline=True` when coordinate map file exists (mocked `SEED_MAPS_DIR`)
- `has_seed_centreline=False` when no coordinate map file
- T10/T11 complex still in Daytona YAML (integrity check)
- `TrackMapDrawData.seed_centreline` field exists and defaults to `[]`
- `project_to_screen` preserves seed_centreline count
- `format_geometry_alignment_summary` returns "—" for None; mentions "unavailable"; shows "mean err" when data available
- `format_alignment_summary` returns `geometry_match` key for both None and non-None results
- Identity transform on identical point sets: translation ≈ 0, scale ≈ 1
- `_compute_coord_errors` returns 0.0 for identical inputs
- `_apply_transform` identity leaves points unchanged
- Wrong JSON schema → `import_seed_coordinate_map_json` returns None
- Nonexistent file → `import_seed_coordinate_map_json` returns None

---

## Group 17U — Track Library Schema and Seed Data Registry

**New module:** `data/track_library.py` — structured versioned registry replacing ad hoc file discovery.

### Problem solved

After Group 17T, track seed/coordinate files lived in a flat `data/track_seed_maps/` directory with no schema versioning, no per-layout metadata, no semantic model separation, and no availability summary. As the track library grows this is unmanageable.

### Three-layer model extension

| Layer | Name | Format | What it contains |
|-------|------|--------|-----------------|
| 0 | Track Library Index | JSON (`index.json`) | Which tracks are registered |
| 1 | Track Metadata | JSON (`track.json`) | Country, GT7 code, layout list |
| 1.5 | Layout Manifest | JSON (`manifest.json`) | lap_length_m, availability flags, asset pointers |
| 1.6 | Semantic Model | JSON (`semantic_model.json`) | Corners, sectors, complexes (separated from geometry) |
| 1.7 | Validation Rules | JSON (`validation_rules.json`) | Per-layout acceptance thresholds |
| 1.8 | Source Manifest | JSON (`source_manifest.json`) | Data provenance, estimated vs verified fields |
| 1.9 | Seed Geometry | JSON (`geometry.seed_map.json`) | Coordinate data (schema `seed_coordinate_map_v1`) |

### Directory structure

```
data/track_library/
  index.json                              ← schema: track_library_index_v1
  tracks/
    daytona_international_speedway/
      track.json                          ← schema: track_metadata_v1
      layouts/
        daytona_international_speedway__road_course/
          manifest.json                   ← schema: track_layout_manifest_v1
          semantic_model.json             ← schema: track_semantic_model_v1
          validation_rules.json           ← schema: validation_rules_v1
          source_manifest.json            ← schema: source_manifest_v1
          geometry.seed_map.json          ← NOT YET PRESENT for Daytona
          accepted_models/                ← future accepted model snapshots
          calibration_runs/               ← future calibration run archives
```

### Key dataclasses

**`TrackLibraryAvailability`:**
```python
metadata: bool = True
sectors: bool = False
corner_windows: bool = False
corner_complexes: bool = False
seed_geometry: bool = False    # ← False for Daytona until geometry file added
width_model: bool = False
accepted_model: bool = False
calibration_runs: bool = False
```

**`TrackLibraryAuditResult`:**
```python
library_available: bool = False
manifest_loaded: bool = False
semantic_model_loaded: bool = False
validation_rules_loaded: bool = False
seed_geometry_in_library: bool = False
seed_geometry_legacy: bool = False
availability: Optional[TrackLibraryAvailability] = None
seed_coordinate_source: str = "none"   # "track_library"/"legacy_fallback"/"none"
warnings: list = field(default_factory=list)
```

### Resolver pattern

`resolve_seed_coordinate_map(track_id, layout_id, base_dir=None)` → `(SeedCoordinateMap|None, source_label)`:
1. Try library `geometry.seed_map.json` → source label = `"track_library"`
2. Fall back to `data/track_seed_maps/<id>__<id>.seed_map.json` → `"legacy_fallback"`
3. Neither found → `(None, "none")`

### `SeedAuditResult` extension

New fields (all default to safe values; existing callers unaffected):
```python
seed_source:             str  = "none"   # "track_library"/"legacy_fallback"/"none"
library_manifest_loaded: bool = False
validation_rules_loaded: bool = False
```

### `format_alignment_summary()` extension

New `"seed_source"` key in returned dict:
- `"Track library"` when geometry found in library
- `"Legacy fallback"` when geometry found in `data/track_seed_maps/`
- `"Unavailable"` when no geometry found anywhere
- `"—"` when result is None (no alignment computed yet)

### Daytona Road Course library skeleton (2026-06-26)

| Asset | Status |
|-------|--------|
| `manifest.json` | ✅ Present — `lap_length_m=5729.0`, `availability.seed_geometry=false` |
| `semantic_model.json` | ✅ Present — 12 corners T1–T12, 3 sectors S1–S3, 2 complexes |
| `validation_rules.json` | ✅ Present — `max_lap_delta_pct=5.0`, `require_corner_windows=true` |
| `source_manifest.json` | ✅ Present — T1 apex 8.2% verified; all other windows estimated |
| `geometry.seed_map.json` | ❌ NOT YET PRESENT — acceptance remains blocked |

### To create Daytona geometry file

1. Drive accepted calibration laps in GT7 exporting x/y per station.
2. Use `export_seed_coordinate_map_json()` from `data/track_seed_coordinate_map.py` to produce the file.
3. Place at `data/track_library/tracks/daytona_international_speedway/layouts/daytona_international_speedway__road_course/geometry.seed_map.json`.
4. Set `"seed_geometry": true` in `manifest.json` availability.

### Test coverage

83 tests in `tests/test_group17u_track_library_schema.py` covering 13 categories:
- Track library index loads and validates schema
- Daytona manifest loads with correct lap_length_m and display name
- Semantic model contains 12 corners, 3 sectors, 2 complexes
- Validation rules load with correct thresholds
- Missing geometry reported cleanly (no uncaught exceptions)
- Resolver prefers library over legacy
- Resolver falls back to legacy when library geometry missing
- Resolver returns `(None, "none")` when neither source available
- Seed audit reports correct `seed_source` value for each scenario
- Layout availability flags are correct for Daytona
- Validation rules thresholds match spec
- Library manifest lap_length_m matches YAML seed lap_length_m
- Semantic model corner/sector count matches YAML seed definitions
- BusStop and T10T11 complexes with correct member lists
- Source manifest has sources and fields_estimated
- `TrackLibraryAuditResult` reports all four loaded flags correctly
- Missing track in index → warning recorded in audit result
- `SeedAuditResult` new fields default correctly for None/no-IDs cases
- `format_alignment_summary` includes `seed_source` key in all code paths
- Recalibration blocker text references "lap" and clean-lap guidance

---

## Group 18A — Track Truth Library, Calibration Wizard, Station-Based Map Matching (2026-07-03)

### The problem this solves

Every group up to 17U still let the app treat **curvature-only detected corners** as if
they were authoritative track truth. A curvature peak is a guess, not a mapped corner.
Group 18A introduces a proper **Track Truth spine** and the product principle behind it:

> **No mapped-corner confidence ⇒ no high-confidence setup/strategy recommendation.**

This is the **foundation only** — the Setup Brain, Strategy Brain, and Live Race Engineer
are **not** rewired to consume Track Truth yet (deferred, see below).

### The Track Truth model (`data/track_truth.py`)

Pure-Python, no PyQt6. The authoritative geometry description for one layout.

**Enums** (all `(str, Enum)`):
- `TrackTruthStatus`: `NO_DATA`, `METADATA_ONLY`, `CURVATURE_PROVISIONAL`, `ACCEPTED_SEED_MAP`, `ACCEPTED_LIVE_MAPPING`
- `TrackTruthConfidence`: `NONE`, `LOW`, `MEDIUM`, `HIGH`
- `TrackTruthSource`: `ESTIMATED`, `TELEMETRY_CAPTURED`, `ENGINEER_VALIDATED`
- `TrackTruthValidationIssue`: `NON_MONOTONIC_STATIONS`, `PROGRESS_OUT_OF_RANGE`, `LAP_LENGTH_ZERO_OR_NEG`, `APEX_OUTSIDE_WINDOW`, `COMPLEX_MISSING_MEMBER`, `SECTOR_PROGRESS_OUT_RANGE`, `CORNERS_EXPECTED_NO_WINDOWS`, `NO_COORDINATE_GEOMETRY`, `SINGLE_MEMBER_COMPLEX`

**Dataclasses:** `TrackStation`, `CornerWindow`, `CornerComplex`, `SectorMarker`,
`PitLaneDefinition`, `TrackTruthManifest`, `TrackTruthModel`, `TrackTruthValidationResult`.
Field lists are documented in `docs/TRACK_LIBRARY_SCHEMA.md` (Track Truth Model Schema).

**Schema constants:** `TRUTH_MODEL_SCHEMA="track_truth_model_v1"`,
`TRUTH_MANIFEST_SCHEMA="track_truth_manifest_v1"`.

**Functions:** `track_truth_model_to_dict`, `track_truth_model_from_dict` (returns `None` on
schema mismatch, never raises), `export_track_truth_model_json`, `import_track_truth_model_json`,
`resolve_track_truth_model(track_id, layout_id, base_dir=None)`,
`validate_track_truth_model(model)`, `can_use_track_truth_for_ai_corner_context(result)`.

**Runtime-built, not stored:** `resolve_track_truth_model()` builds the model at runtime from
the **existing** library `manifest.json` + `semantic_model.json` (and the coordinate seed map
when present). **No new JSON file is added to the library.**

### Validation gates — the heart of the spine

`validate_track_truth_model(model)` returns a `TrackTruthValidationResult` with three tiered
gates:

| Gate | True when |
|------|-----------|
| `is_accepted` | **no blockers** |
| `is_usable_for_live_mapping` | `is_accepted` AND stations present AND `manifest.corners_are_seed_verified` |
| `is_usable_for_ai_corner_context` | `is_usable_for_live_mapping` AND `manifest.seed_geometry_available` |

**Blockers** (each prevents `is_accepted`):
- non-monotonic station distances
- station/sector progress out of 0–100
- `lap_length_m ≤ 0`
- apex outside its corner window
- complex referencing a missing corner ID
- `corners_expected > 0` but no corner windows
- **`NO_COORDINATE_GEOMETRY`** — exact text: *"Coordinate geometry unavailable — high-confidence corner mapping is blocked"*

**Warning (not a blocker):** single-member complex.

`corners_are_seed_verified` and `seed_geometry_available` both default to **False** — they
are explicit growth fields. Until a real accepted seed geometry sets them, corners stay
provisional/unverified.

**AI guard:** `can_use_track_truth_for_ai_corner_context(result)` returns `True` only when
the model `is_accepted` AND `is_usable_for_ai_corner_context`; a `None` result → `False`.

**Honesty guarantees:** `summary` never contains the word "accepted" when the model is not
accepted; a **rejected** model that still has some geometry gets `status = NO_DATA` (never a
provisional/accepted status).

### How this supersedes curvature-only corner detection

The older pipeline (Group 17E–17T) detected corners from curvature peaks in telemetry and,
absent seed windows, could present them as though they were verified. Track Truth replaces
that as the *source of corner truth*:

- Corners derived from curvature alone are `CURVATURE_PROVISIONAL` / unverified and can never
  reach an accepted status without seed geometry.
- Corner truth now comes from the semantic model's corner **windows** + coordinate **stations**,
  validated by the gates above, not from curvature ranking.
- A corner section that coaching treats as one unit (e.g. Daytona's `Horseshoe` = T10 + T11)
  is one `CornerComplex`, so the app no longer needs to treat it as two separate detected
  corners.

### Station-based map matching (`data/track_truth_matcher.py`)

The live map-matching **foundation** — a scoring scaffold designed to be swapped for
HMM/Viterbi later. Never raises.

- `TrackTruthMatchInput`, `TrackTruthMatchResult`,
  `match_track_truth_position(inp, model, validation=None) -> TrackTruthMatchResult`.
- Weighted candidate scoring (private `_score_candidate`): spatial distance + heading
  agreement + monotonic-progress-from-previous + lap-wrap handling + max-plausible-movement
  + pit awareness.
- Confidence bands mirror `data/track_map_matching.py`: ≤5 m HIGH, ≤20 m MEDIUM, ≤60 m LOW,
  else NONE. Pit likely when speed < 8 kph or distance > 60 m.

### Calibration wizard (`data/track_truth_calibration.py`)

The calibration wizard **foundation** — a controller that walks a driver through capturing
geometry and accepting it into the library.

- `TrackTruthWizardStage`: `NOT_STARTED`, `CAPTURE_CENTRELINE`, `CAPTURE_LEFT_EDGE`,
  `CAPTURE_RIGHT_EDGE`, `OPTIONAL_HOT_LAP`, `BUILD_PROPOSED`, `VALIDATE`, `ACCEPT`.
- `TrackTruthWizardState`, controller `TrackTruthCalibrationWizard`.
- **Illegal transitions are no-ops** that set `state.error` (never raise).
- `accept()` is the **only** route to `ACCEPT`; it persists via
  `save_seed_geometry_to_library` and `advance()` delegates `VALIDATE → ACCEPT` to it.
- **Geometry building is delegated**, not duplicated: a defensive wrapper around
  `data/track_geometry_builder.build_seed_geometry` (try/except → `can_generate` False on any
  error) — no second geometry algorithm exists. (Builds on the `track_geometry_builder`
  module introduced with the Group 17V / track-geometry work.)
- `abandon()` resets to `NOT_STARTED`, clears capture sessions, writes no file.

### UI (Track Modelling tab — headless-VM tested only)

- `ui/track_modelling_vm.py`: pure-Python `format_track_truth_status(model, validation,
  track_id=None, layout_id=None) -> dict` returning a 20-key display dict (value + `_color`
  keys), with a full `"—"` / `"#888888"` placeholder for the `None` case. Four display states:
  metadata-only / curvature-provisional / accepted-seed-map / accepted-live-mapping. Uses the
  terms **"Track Truth"**, **"Map Alignment"**, **"Live Mapping Ready"**; avoids "lap offset
  calibration".
- `ui/track_modelling_ui.py`: a **"Track Truth / Mapping"** QGroupBox panel (selected
  track/layout, track-library availability, coordinate seed-map availability, corner/complex
  metadata availability, geometry acceptance status, live-map-matching readiness, AI corner
  context readiness, blockers, warnings) refreshed by `_tm_refresh_track_truth_panel()`, wired
  into `_tm_on_layout_changed`, `_tm_run_alignment`, `_tm_accept_track_model`,
  `_tm_rebuild_model`, and `_tm_try_load_accepted_model`.
- Per project convention this panel has **headless VM tests only** (no Qt test) — needs manual UAT.

### How this fixes the Daytona / curvature problem

- Daytona Road Course truth is built at runtime from its existing manifest + semantic model
  (12 corners T1–T12, sectors S1–S3, complexes BusStop = T1+T2 and Horseshoe/T10T11 = T10+T11).
- Daytona has **no** `geometry.seed_map.json`, so its Track Truth model has **zero stations** ⇒
  validation returns the `NO_COORDINATE_GEOMETRY` blocker ⇒ `is_accepted = False` ⇒ AI corner
  context is **BLOCKED**. Curvature peaks are therefore never presented as verified truth.
- `availability.seed_geometry` stays `false` — no code flips it.

### Known limitations

- Daytona corner/sector positions are `source="estimated"`, `confidence="low"` (only the T1
  apex is verified) — they are metadata, not accepted geometry.
- Live map matching is a scoring scaffold, not yet HMM/Viterbi.
- The Track Truth panel has headless VM tests only — no Qt test — pending manual UAT.

### Deferred (natural next steps)

- Wire the `TrackTruthModel` into the Setup Brain / Strategy Brain / Live Race Engineer so
  recommendations respect the "no mapped corner ⇒ no high-confidence rec" principle.
- Full HMM/Viterbi matcher (only the scoring scaffold shipped).
- Produce a real Daytona `geometry.seed_map.json` (acceptance stays blocked until it exists).
- Add any non-Daytona track; automated track-boundary generation; deep AI prompt integration;
  automatic track identification.

### Test coverage

**45 new tests total:**
- `tests/test_group18a_track_truth.py` — 26 tests (model, validation gates, AI guard, JSON round-trip)
- `tests/test_group18a_track_truth_matcher.py` — 9 tests (candidate scoring, confidence bands, pit awareness)
- `tests/test_group18a_track_truth_calibration.py` — 10 tests (wizard stages, illegal transitions, delegated build/accept)

Full suite after Group 18A: **4053 pass / 6 skip / 0 fail.**

---

## DEF-17U-UAT-007 — Calibration Pit-In Detection Disabled by Default (2026-07-03)

**Automatic pit-in classification is now disabled by default for calibration** because GT7
provides no reliable pit-lane signal. `TelemetrySample.is_in_pit_lane` is always `None` (no
per-sample pit-lane flag in the GT7 Custom UDP packet — see the calibration quality-rules and
GT7-limitations notes above), so pit-in could only ever be *inferred* geometrically. That
inference (`detect_pit_lap_raw()`, a contiguous XZ run > 60 m from the lap centroid for > 10 s)
false-positived on normal GT7 **Time Trial** laps, wrongly rejecting clean laps and failing the
reference-path build.

**Change:** `build_reference_path(session, *, pit_detection_enabled=False)` — pit-in detection
is **opt-in**. `detect_pit_lap_raw()` is only called, and "pit-in" wording only emitted, when a
caller explicitly passes `pit_detection_enabled=True`. This means the `pit lane > 10%` rejection
rule listed in the calibration quality table above is inactive unless pit detection is opted in.

**Related partial-lap handling:** the same fix added `PARTIAL_START` / `PARTIAL_STOP`
`CalibrationLapQuality` values so short first/last laps (captured when Start/Stop is pressed
mid-lap) are recognised as partial slices — excluded from the build, not counted as rejected —
instead of poisoning the session median or being mislabelled as outliers. The session median is
computed from complete (non-partial) laps only. Full detail: `MASTER_TESTING_REGISTER.md`
(DEF-17U-UAT-007) and `docs/TRACK_MODELLING_RUNTIME_UAT.md` (DEF-17U-UAT-007).
