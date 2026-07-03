# GT7 VR Dashboard — Project State

> Last updated: 2026-07-03 (Diagnostic Tab Cleanup — Low-Risk UI Dags Removal. DELETED the 7 hidden never-connected legacy per-segment review buttons + unreachable handlers + dead imports (`ui/track_modelling_ui.py`; pure review functions retained) and the dead never-rendered `_TELEMETRY_REFERENCE_HTML` constant; RENAMED "Race Config ID"→"Session Match Key", Diagnostics "Rem(clk)"/"rem_ms(raw)"/"Ann queue"→"Time left:"/"remaining_time_ms:"/"Voice queue:", window title + Guide h1 → "Next Gear Racing Pit Crew"; Guide fixed (phantom "Dashboard" Step 8 → real Home tab, API-key bullet → Strategy Builder, new ⚙ tool-tabs note, pip-install tooltip removed). No tab order/logic/prompt/fan-out change (pinned by tests). `docs/DIAGNOSTIC_TAB_CLEANUP.md` (NEW). **Full suite 4479 pass / 6 skip / 0 fail** (25 new tests; group24 `_tm_` floor 54→46). Prior: Home Dashboard Build — Race Engineer Command Centre. New `ui/home_dashboard_vm.py` (pure display view model — five cards: Race Setup / Track Intelligence / Setup Brain / Strategy Brain / AI Input Safety, plus the Next Best Action from `build_flow_state_summary()`; never raises; reads only the four canonical contexts + AI snapshot core) rendered by a new **Home tab appended at index 13** in `ui/dashboard.py` (indices 0–12 unchanged; refresh on tab-shown + guarded hooks; no polling/workers; display-only — home methods write nothing, source-scanned). Plain-English stale indicators (setup-vs-event, setup-vs-strategy, strategy-vs-event, track mismatch, AI legacy fallback) now visible in the UI. `docs/HOME_DASHBOARD_BUILD.md` (NEW). **Full suite 4454 pass / 6 skip / 0 fail** (52 new tests). Prior: AI Snapshot Migration — Frozen Context Inputs. New `data/ai_context_snapshot.py` (frozen, owner-documented AI-input snapshots composing the four canonical contexts: `StrategyAISnapshot`/`PracticeAnalysisSnapshot` race-params + `SetupAISnapshot`; byte-identical to the legacy expressions when stores are in sync — proven incl. a byte-identical `_build_race_prompt` text test; fresh DB event values supersede stale fan-out copies as the documented intentional difference; staleness detected at build time) + `docs/AI_SNAPSHOT_MIGRATION.md`. Migrated: `_assemble_strategy_inputs`, `_run_ai_analysis`, `_run_practice_analysis` (DEF-P1-005 default preserved), `_run_build_setup` (+ worker-thread rec metadata frozen), `_setup_analyse_ai`. No prompt wording/intelligence changed; legacy stores retained. **Full suite 4402 pass / 6 skip / 0 fail** (41 new tests; 20 legacy scans updated). Prior: State Consolidation 4 — TrackContext (`data/track_context.py`, 68 tests); 3 — SetupContext; 2 — StrategyContext; 1 — EventContext)
> Read this file first, then MASTER_TESTING_REGISTER.md, before touching any code.
>
> Note: this file's group table below was authored through Group 17U. Groups 17V–38, the
> lettered groups (A/B/C/D/E), Qualifying Mode, and the Setup Brain + Strategy Outcome
> integration are catalogued in `MASTER_TESTING_REGISTER.md` (see its "Groups 26–38 +
> Lettered Groups" and "Integration" sections) and in `docs/CURRENT_CLAUDE_HANDOFF.md`.
> The build-status total below is current (4053).

---

## Current Build Status

| Metric | Value |
|--------|-------|
| Automated tests | 4479 passed / 6 skipped / 0 failed |
| Latest work | Diagnostic Tab Cleanup (`docs/DIAGNOSTIC_TAB_CLEANUP.md`) — 7 legacy per-segment buttons + unreachable handlers deleted, dead telemetry-reference constant deleted, "Session Match Key" rename, Diagnostics label wording, product-name branding, Guide fixes (real Home tab step, API-key location, ⚙ tool-tabs note) — 25 new tests |
| Prior work | Home Dashboard Build — 52 tests. AI Snapshot Migration — 41 (+20 legacy scans updated). State Consolidation 4 — TrackContext — 68. 3 — SetupContext — 67. 2 — StrategyContext — 53. 1 — EventContext — 38. Product Consolidation — 27 |
| Latest fix | DEF-17U-UAT-007 — Time Trial calibration builds correctly; pit-in detection OFF by default, new PARTIAL_START/STOP lap quality (`data/track_calibration.py`, `ui/track_modelling_vm.py`, `ui/track_modelling_ui.py`, `data/track_segment_detection.py`) |
| Latest group | Group 18A — Track Truth foundation (`data/track_truth.py`, `track_truth_matcher.py`, `track_truth_calibration.py`) — 45 new tests |
| Last test run | 2026-07-03, DEF-17U-UAT-007 — new tests `test_def17u_uat007_calibration_build.py` (~35), `test_def17u_uat007_partial_laps.py` (44) |
| App launches | Yes (no startup crash) |

---

## Architecture Stabilisation — Group Status

| Group | Focus | Status | Key Defects |
|-------|-------|--------|-------------|
| Group 1 | Crash fixes | Complete + UAT Passed | DEF-P1-003, DEF-P1-004, DEF-P1-008 |
| Group 2 | AI prompt accuracy + data persistence | Complete — UAT: Groups 2–4 failed, Groups 1+5 passed | DEF-P1-005 through DEF-P2-016 |
| Group 3 | Session reload accuracy | Complete — Partially fixed: DEF-P2-013, DEF-P2-014 re-opened | DEF-P1-002, DEF-P2-011–DEF-P2-014 |
| Group 4 | BoP and tuning permissions | Complete — Partially fixed: DEF-P1-005 blocked by Root Cause A | DEF-P2-004–DEF-P2-008 |
| Group 5 | Live mode + voice guards | Complete + UAT Passed | DEF-P2-001, DEF-P2-002, DEF-P2-008, DEF-P2-QRF |
| Group 6 | UI placement + data quality | Complete + AWR pending | DEF-P2-010, DEF-P2-015 |
| Group 7 | Event persistence (Root Cause A) | **Complete — Awaiting Retest** | DEF-P1-009 |
| Group 8 | Session reload mapping (Root Cause B) | **Complete — Awaiting Retest** | DEF-P2-013, DEF-P2-014, DEF-P2-009 |
| Group 9 | AI Debug / Log visibility (Root Cause C) | **Complete — Awaiting Retest** | DEF-P1-010 |
| Group 10 | AI Prompt BoP Context (test coverage only) | **Complete — Awaiting Retest** | DEF-P1-005, DEF-P2-007, DEF-P2-016 |
| Group 11 | UI Display Fixes (smoke test regressions) | **Complete — AWR-040/041 pending retest** | DEF-P1-011, DEF-P2-021 |
| Group 12 | BoP tuning fix + History mapping investigation + AI Log display | **Complete — AWR-042/043/044 pending runtime** | DEF-P1-005 ✅, DEF-P2-013/014 ✅, DEF-P2-021 ✅, DEF-P2-022 closed |
| Group 13 | Live session defects: pit detection, save-session, compound propagation, live tyre | **Complete — AWR-045–049 pending runtime** | DEF-P2-023 ✅, DEF-P2-024 ✅, DEF-P2-025 ✅, DEF-P2-019/026 ✅, DEF-P2-020/027 ✅ |
| Group 14 | UAT no-go remediation: BoP prompt, None stats, session dupe, qualifying PIT_EXIT, AI log timer, UTC timestamp, Garage setups | **Complete — AWR-050–057 pending runtime** | DEF-P1-012 ✅, DEF-P2-029 ✅, DEF-P2-030 ✅, DEF-P2-031 ✅, DEF-P2-032 ✅ (regression), DEF-P2-033 ✅, DEF-P2-034 ✅, DEF-P2-035 ✅ |
| Group 15 | AI context remediation: RaceParams bop/avail_tyres, practice worker car_id, PTT car context, practice BoP/feedback/prev-AI, race prompt timed race, build_car_setup race context, data quality note, strategy validation | **Runtime-validated 2026-06-23 — AWR-058–067/069 CLOSED; AWR-063/068 blocked by DEF-P3-013 (fixed Group 15A)** | DEF-P1-013 ✅, DEF-P1-014 ✅, DEF-P2-036 ✅, DEF-P2-037 ✅, DEF-P2-038 ✅, DEF-P2-039 ✅, DEF-P2-040 ✅, DEF-P2-041 ✅ (via 15A), DEF-P3-009 ✅, DEF-P3-010 ✅, DEF-P3-011 ✅, DEF-P3-012 ✅ |
| Group 15A | DEF-P3-013 fix: AILogEntry car_id/track fields + threading through all AI callers | **Complete 2026-06-23 — AWR-063 CLOSED; 56 tests pass** | DEF-P3-013 ✅ |
| Group 16 | Phase 2: Per-lap telemetry in practice prompt (2-A), fuel sequence trend in strategy prompt (2-B), compound degradation sequences in strategy prompt (2-C), tyre temp per lap schema migration v3 + recorder + DB (2-D) | **Complete 2026-06-23 — 74 tests pass** | — |
| Group 17 (user: Group 16) | Corner-Level Telemetry Learning: CornerIssue model, PATH A (event_positions_json), PATH B (frame-level), fix verification, setup advice bridge, AI prompt injection, schema v4 (corner_issues table) | **Complete 2026-06-23 — 64 tests pass** | — |
| Group 18 | DEF-P3-014: Startup residual strategy/race config activation — removed auto-set_plan() and auto-set_race_config() from main.py startup; removed tracker push from _update_race_config(); fixed telemetry.tracker → telemetry.state import in _on_event_set_active() | **Complete 2026-06-23 — 21 tests pass** | DEF-P3-014 ✅ |
| Group 17A | Track Intelligence Seed Loader: `data/track_intelligence.py` — TrackModellingStatus enum (9 values + helper methods), typed dataclasses, seed loader with validation, 5 query functions, AI prompt context helper, caching | **Complete 2026-06-24 — 63 tests pass** | — |
| Group 17B | Track Modelling UI tab (tab #12): `ui/track_modelling_vm.py` view model (11 functions, no PyQt6), `_build_track_modelling_tab()` in dashboard.py — QSplitter with search, cascaded combos, 5 detail panels (facts/readiness/car/prompt), lazy seed load on tab show | **Complete 2026-06-24 — 101 tests pass** | — |
| Group 17C | Calibration Lap Capture + Reference Path Builder: `data/track_calibration.py` — TelemetrySample, CalibrationLap, CalibrationSession, ReferencePathPoint, ReferencePath, CalibrationBuildResult, quality evaluator (7 reject rules), 6 distance/progress helpers, `build_reference_path()`, JSON export/import; disabled UI placeholders in Track Modelling tab | **Complete 2026-06-24 — 102 tests pass** | — |
| Group 17D | Live Telemetry Calibration Session Wiring: `data/track_calibration_runtime.py` — `can_capture_calibration_sample`, `infer_lap_number`, `packet_to_calibration_sample` adapter, `CalibrationCaptureState` enum, `TrackCalibrationCaptureController` state machine (5 states, 7 public methods, 5 button-state properties); `SignalBridge.calibration_packet` signal; 4 live buttons + 5 status labels in Track Modelling tab; `_cal_pkt_counter` 10 Hz subsampling in `main.py` | **Complete 2026-06-24 — 81 tests pass** | — |
| Group 17E | Automatic Track Segment Detection: `data/track_segment_detection.py` — 3 enums (`TrackSegmentType` 12 values, `TrackSegmentDirection`, `TrackSegmentDetectionConfidence`), 3 dataclasses (`DetectedTrackSegment`, `SegmentDetectionResult`, `SegmentDetectionConfig`), 7 private helpers, per-lap detection (`detect_segments_from_lap`), multi-lap aggregation (`detect_track_segments`), corner numbering (`assign_corner_numbers`), 4 auxiliary detectors (limiter, kerb, gear, fuel-save), JSON export/import; "Detect Segments" button + 3 status labels in Track Modelling tab | **Complete 2026-06-24 — 99 tests pass** | — |
| Group 17F | Segment Review and Track Model Approval: `data/track_segment_review.py` — 2 enums (`SegmentReviewStatus` 8 values, `SegmentReviewAction` 7 values), 2 dataclasses (`ReviewedTrackSegment`, `TrackModelReviewResult`), 7 action functions, `review_completion_pct`, `is_ai_ready` (5-blocker rule set), JSON export/import; 3 view-model helpers in `track_modelling_vm.py`; Segment Review QGroupBox (8-col table, 6 action buttons, save), Review Approval QGroupBox (7 stat labels) in Track Modelling tab | **Complete 2026-06-24 — 122 tests pass** | — |
| Group 17G | Approved Track Model Resolver and Modelling Status Promotion: `data/track_model_resolver.py` — 2 enums (`TrackModelSourceType` 6 values, `TrackModelResolutionStatus` 6 values), 2 dataclasses (`ResolvedTrackModel`, `TrackModelResolverResult`), 4 discovery functions, `resolve_best_track_model` (priority: engineer_validated > ai_ready > reviewed > seed > missing), `build_resolved_track_context_for_prompt` (not yet wired to AI); `modelling_status` added to reviewed JSON schema (backward-compatible); `format_resolver_summary` in vm; "Resolver Status" QGroupBox in Track Modelling tab (refreshes on layout select + after save) | **Complete 2026-06-24 — 68 tests pass** | — |
| Group 17H | Track Intelligence AI Prompt Integration: `strategy/track_context_prompt.py` — `get_track_context_for_ai(loc_id, lay_id)` helper (never raises, delegates to resolver); `track_location_id`/`layout_id` fields added to `RaceParams`; track context injected into `_build_race_prompt`, `_build_practice_prompt`, `_build_setup_from_scratch_prompt`, `build_car_setup`, `DrivingAdvisor._build_coaching_prompt`, `_build_setup_prompt`, `_build_combined_prompt`; `config["strategy"]["track_location_id"/"layout_id"]` set by Track Modelling tab selection; structured_payload debug metadata includes `track_context_included` flag; seed-only/not-AI-ready/missing context all preserved with appropriate warnings | **Complete 2026-06-24 — 56 tests pass** | — |
| Group 17I | Telemetry Issue to Segment Enrichment: `data/track_issue_enrichment.py` — `TrackIssueType` (10), `TrackIssuePhase` (7), `TrackIssueEnrichmentConfidence` (4) enums; `RawTelemetryIssue`, `EnrichedTelemetryIssue`, `TrackIssueEnrichmentResult` dataclasses; `enrich_telemetry_issues()` with priority matching (segment_id > lap_progress > distance > XYZ nearest > nearest midpoint > unresolved); confidence rules (model source × segment status × match method); deterministic implication mapping for 7 issue+segment combinations; `issues_from_lap_stats()` adapter (5 position list types); `issues_from_corner_issues()` adapter (decodes corner_id grid buckets); `summarise_enriched_issues_for_prompt()` (never invents corner names for unresolved); `DrivingAdvisor._get_enriched_issue_context()` wired into coaching/setup/combined prompts | **Complete 2026-06-24 — 76 tests pass** | — |
| Group 17J | Live Current Segment Resolver: `data/live_segment_resolver.py` — `LiveSegmentResolutionConfidence` (4), `LiveSegmentResolutionStatus` (6) enums; `LivePosition`, `LiveSegmentMatch`, `LiveSegmentResolverResult`, `LiveSegmentResolverConfig` dataclasses; `resolve_live_segment()` with priority matching (segment_id exact > lap_progress range > distance_along_lap_m via ref path > XYZ nearest via ref path > nearest midpoint > unresolved); GT7 limitations documented (no native lap_progress, road_distance is absolute — not used as distance_along_lap_m); `packet_to_live_position()` adapter (duck-typed, guards paused/loading/off-track/zero-xyz, never raises); `format_live_segment_for_engineer()` (compact wording, no invented names); `get_live_segment_context_for_prompt()` (AI block, returns "" for no_reviewed_model); `DrivingAdvisor._get_live_segment_context(live_position=None)` wired into coaching/setup/combined prompts via optional live_position param | **Complete 2026-06-24 — 78 tests pass** | — |
| Group 17K | Segment-Aware Live Coaching Rules: `data/live_segment_coaching.py` — `LiveCoachingCueType` (13 values incl. no_call), `LiveCoachingPriority` (4), `LiveCoachingSuppressionReason` (12) enums; `LiveCoachingCue`, `LiveCoachingDecision`, `LiveCoachingConfig` dataclasses; 25-entry cue template table covering brake_lock/wheelspin/oversteer/understeer/poor_exit_drive/wrong_gear/limiter_hit/fuel_save/tyre_wear (exact + fallback segment-type rules); `build_live_coaching_decision()` — deterministic rule engine with confidence gate (suppress on LOW/UNKNOWN by default), segment quality gate (seed_only/rejected/needs_more_laps → suppress), repetition gate (min_issue_repetitions=2), cooldown (suppress same cue_type+segment within N laps), max_cues_per_lap cap; `format_live_coaching_for_prompt()` (returns "" when suppressed, compact block with basis when cue fires); `get_live_coaching_debug_metadata()` (4 debug fields); `DrivingAdvisor._get_live_coaching_context(live_position, laps)` wired into coaching prompt extra_sections | **Complete 2026-06-24 — 78 tests pass** | — |
| Group 17L | Lap-Start Offset Calibration and Road-Distance Mapping: `data/lap_distance_mapper.py` — `LapDistanceMappingStatus` (6), `LapDistanceMappingConfidence` (4) enums; `LapStartOffsetCalibration`, `LapDistanceMappingResult`, `LapDistanceMapperConfig` dataclasses; `normalise_distance()` (modulo, handles negatives), `calculate_lap_start_offset()`, `map_road_distance_to_lap_distance()`, `map_road_distance_to_lap_progress()` (0.0–1.0 clamped); `create_offset_zero()`, `create_offset_from_reference_path()`, `load_offset_calibration_for_track()`; JSON export/import (`<loc>__<lay>__lap_offset.json`); `live_segment_resolver.py` updated: `LivePosition.road_distance_m` field added, `packet_to_live_position()` populates it, `enrich_position_with_road_distance()` added, `resolve_live_segment(offset_calibration=None)` adds Priority 3 road_distance mapping (confidence downgraded when LOW/UNKNOWN calibration) | **Complete 2026-06-24 — 69 tests pass** | — |
| Group 17M | Runtime UAT and Calibration Workflow Hardening: `ui/track_modelling_vm.py` extended — `_WORKFLOW_ERROR_MESSAGES` dict (11 keys), `get_workflow_error_message()`, `get_calibration_button_states()` (15-key dict, all 5 controller states, offset buttons), `format_calibration_status_extended()` (packet age, sample count, path info), `format_lap_offset_status()` (provisional/validated, warnings, notes), `format_live_resolver_status_summary()` (multi-line status string); `data/track_modelling_runtime_check.py` — `RuntimeCheckResult` dataclass, `run_track_modelling_runtime_check()` (never raises, duck-typed); `data/lap_distance_mapper.py` — `create_offset_zero()` updated to default source="zero_offset" and validate positive length; `ui/dashboard.py` — packet age label, Lap Offset Calibration QGroupBox (Create/Load/Save buttons, status/detail/warning labels), `_tm_last_packet_time` tracking, `_tm_get_track_length_m()`, `_tm_update_packet_age_label()`, `_tm_update_offset_status()`, `_tm_create_zero_offset()`, `_tm_load_offset()`, `_tm_save_offset()`, signal connections; `docs/TRACK_MODELLING_RUNTIME_UAT.md` — 15-section manual UAT checklist | **Complete 2026-06-24 — 94 tests pass** | — |
| Group 17M UAT | DEF-17M-UAT-001/002/003 remediation: `ui/track_modelling_vm.py` — `format_lap_count_info()` (captured/quality/explanation text), `format_file_audit_status()` (saved/detail/load_status/extras text); `data/track_calibration.py` — `reference_path_filename()`, `TrackModelFileAudit` dataclass, `audit_track_model_files()` (never raises); `ui/dashboard.py` — `_tm_update_cal_status()` uses format_lap_count_info, `_tm_detect_segments()` split into outer catcher + `_tm_detect_segments_safe()` with seed_result.layouts crash fixed, `_tm_on_layout_changed()` calls `_tm_audit_and_show_saved_files()`, new `_tm_audit_and_show_saved_files()` method | **Complete 2026-06-25 — 49 tests pass** | DEF-17M-UAT-001 ✅, DEF-17M-UAT-002 ✅, DEF-17M-UAT-003 ✅ |
| Group 17N UAT-005 | DEF-17N-UAT-005 remediation — actionable rejection diagnostics: `data/track_calibration.py` — `build_reference_path()` now mutates `CalibrationLap.quality/quality_reasons` after assessment; `diagnose_calibration_session()` added; `data/track_segment_detection.py` — `_build_no_usable_laps_errors()` helper + `assess_session_laps` import; `ui/track_modelling_vm.py` — `format_build_failure_diagnostics()`, `_min_samples()`; `ui/dashboard.py` — `_tm_build_path()` uses full diagnostics dialog | **Complete 2026-06-25 — 32 tests pass** | DEF-17N-UAT-005 ✅ |
| Group 17N UAT | DEF-17N-UAT-004 remediation — Detect Segments from persisted data after restart: `data/track_calibration.py` — `calibration_laps_filename()`, `export_calibration_laps_json()` (USABLE laps + all TelemetrySample fields), `import_calibration_laps_json()` (reconstructs CalibrationSession), `TrackModelFileAudit` extended with `calibration_laps_exists/usable_count`, `can_detect_segments` property, `is_legacy_ref_path_only` property, audit + summary_line updated; `data/track_calibration_runtime.py` — `save_reference_path()` writes calibration laps JSON alongside ref path (best-effort); `ui/dashboard.py` — `_tm_detect_segments_safe()` three-path logic (active/disk/legacy), `_tm_audit_and_show_saved_files()` laps-aware enable logic and save-path label; `ui/track_modelling_vm.py` — `format_file_audit_status()` includes laps count in detail_text, distinguishes ready/legacy in load_status | **Complete 2026-06-25 — 41 tests pass** | DEF-17N-UAT-004 ✅ |
| Group 17O | Seeded 1m Track Map, Width Corridor, Map Matching, Visual Verification: `data/track_station_map.py` — `StationPoint`, `SeededCorner`, `TrackStationMap`, `resample_path_to_uniform_spacing`, `build_track_station_map`, curvature-based corner detection with placeholder filling for corners_expected guarantee, `export/import_station_map_json`; `data/track_map_matching.py` — `MapMatchConfidence`, `MapMatchResult`, `find_nearest_station_idx`, `match_position_to_map`, `is_likely_outlap`, `map_match_samples`; `data/track_width_model.py` — `WidthObservation`, `WidthEstimate`, width learning from calibration laps, `is_near_left/right_edge`, `unused_track_width_pct`; `ui/track_map_vm.py` (no PyQt6) — `MapPoint`, `CornerLabel`, `CarDot`, `TrackMapDrawData`, `build_track_map_draw_data`, `project_to_screen`; `ui/dashboard.py` — `TrackMapWidget(QWidget)` QPainter canvas, map widget on Track Modelling tab and Live tab, `_tm_try_build_station_map()`, `_tm_update_live_map_dot()` | **Complete 2026-06-25 — 76 tests pass** | DEF-17O-UAT-001/002/003 fixed (UAT Remediation Round 1) |
| Group 17O UAT Round 2 | DEF-17O-UAT-004/005/006/007/008 remediation: `ui/dashboard.py` — fixed `_tm_try_build_station_map()` seed lookup (line 2770 bug: `self._tm_seed_result.layouts` → `get_selected_layout(seed_result, loc_id, lay_id)`); added BRAKING_ZONE/TRACTION_ZONE to `_TELEMETRY_OVERLAY_SEG_TYPES` (car-specific, Porsche RSR warnings); auto-save station map JSON via `export_station_map_json()` after build; added `_tm_try_load_station_map_from_disk()` auto-loaded when layout changes; updated `_tm_lbl_build_info` to show "Path: N pts | Conf: X | Map: N stations / N corners"; updated `_tm_refresh_seg_table()` to populate Turn column from station map SeededCorner by lap_progress proximity (< 15% threshold); updated test file to add 17 new tests for DEF-17O-UAT-004/005/007/008 classes; updated existing DEF-17O-UAT-002 tests to reclassify BRAKING_ZONE/TRACTION_ZONE as overlays | **Complete 2026-06-25 — 40 tests pass** | DEF-17O-UAT-004/005/006/007/008 ✅ |
| Group 17P | Seed-to-Telemetry Track Model Alignment and Whole-Model Acceptance: `data/track_station_map.py` — `_detect_corners()` now caps at corners_expected (no more T13-T36 for Daytona); returns `(official, extra_peaks)` tuple; `TrackStationMap.extra_curvature_peaks` field; JSON I/O updated; `data/track_model_alignment.py` (NEW) — `TrackModelMatchStatus` enum (5 values), `CornerAlignmentResult`, `SectorAlignmentResult`, `TrackModelAlignmentResult` dataclasses, `align_track_model()`, `get_alignment_blockers()`, accepted model JSON persistence; `ui/track_model_alignment_vm.py` (NEW) — `format_alignment_summary()`, `get_acceptance_button_states()`, `format_mismatch_reasons()`, `manual_approval_buttons_enabled()`; `ui/track_map_vm.py` — `TrackMapDrawData.seed_overlay_note` field; `ui/dashboard.py` — Segment Review renamed Segment Diagnostics; 6 per-segment approval buttons hidden; Review Approval panel replaced by Track Model Alignment panel with Accept Track Model button, Rebuild button, alignment metric labels; `_tm_run_alignment()`, `_tm_refresh_alignment_panel()`, `_tm_accept_track_model()`, `_tm_rebuild_model()`, `_tm_try_load_accepted_model()` methods; `tests/test_group17p_alignment.py` (NEW) — 34 tests | **Complete 2026-06-25 — 34 tests pass** | DEF-17P-UAT-001/002/003/004/005/006 ✅ |
| Group 17Q | Seed Corner Position Matching and Acceptance Integrity: `data/seed_corner_matching.py` (NEW) — `CornerMatchStatus` (6 values), `CornerCandidateMatch`, `match_peaks_to_seed_windows()` greedy algorithm; `data/track_intelligence.py` — `SeedCornerDefinition` dataclass, `TrackLayoutSeed.corner_definitions` field, `_parse_corner_def()`, YAML `corners:` key support; `data/track_station_map.py` — `TrackStationMap.seed_corner_positions_available` field, `build_track_station_map()` branches on corner_defs presence (window-based vs top-N); `data/track_model_alignment.py` — 4 new fields on `TrackModelAlignmentResult` (`seed_corner_positions_available`, `corner_position_match`, `corners_matched`, `corner_candidate_matches`), `align_track_model()` computes per-corner MATCHED/NO_CANDIDATE/UNAVAILABLE, caps ACCEPTABLE_MATCH at GOOD_MATCH when no seed positions; `ui/track_model_alignment_vm.py` — 4 new summary keys; `ui/dashboard.py` — 3 new label rows; `tests/test_group17q_seed_corner_matching.py` (NEW) — 29 tests | **Complete 2026-06-26 — 29 tests pass** | DEF-17Q-001/002/003/004/005 ✅ |
| Group 17R | Seed Map Overlay, True Map Alignment, Recalibration Workflow: `ui/track_model_alignment_vm.py` — `format_alignment_summary()` returns explicit `seed_position_status`, `seed_truth_source` keys; `ui/track_map_vm.py` — `seed_overlay_note` field in `TrackMapDrawData`, propagated through `project_to_screen()`; `ui/dashboard.py` — "Seed truth source" alignment row, `_tm_refresh_alignment_panel()` wiring, `_tm_rebuild_model()` clears station map + shows dialog, warning suppression in `_tm_detect_segments_safe()`, tooltip + lap offset note updates; `tests/test_group17r_seed_overlay_alignment.py` (NEW) — 38 tests | **Complete 2026-06-26 — 38 tests pass** | DEF-17R-001/002/003/004/005/006 ✅ |
| Group 17S | Seed Track Definition Authoring, Corner Complexes, True Alignment Gate: `data/track_intelligence.py` — `SeedSectorDefinition`, `CornerComplexDefinition`, `SeedAuditResult` dataclasses, `audit_layout_seed()`, `_parse_sector_def()`, `_parse_complex_def()`, `TrackLayoutSeed.sector_definitions/corner_complexes` fields; `docs/track_modelling_seed/track_modelling_seed.yaml` — Daytona Road Course enriched with 12 corner windows (T1–T12, source:estimated), 3 sector_definitions (S1/S2/S3), 2 corner_complexes (BusStop=T1+T2, T10T11=T10+T11/Horseshoe); `data/track_model_alignment.py` — lap delta > 5% is now a BLOCKER (was a warning); `ui/track_model_alignment_vm.py` — `format_seed_audit_summary()`, `format_alignment_summary(layout_seed=None)` optional param, `seed_audit` key; `ui/dashboard.py` — "Seed data available" alignment row, `_tm_refresh_alignment_panel()` resolves layout_seed for audit, seed-window-based turn assignment in `_tm_refresh_seg_table()`, `_tm_refresh_seg_diagnostics_labels()` called on station map load/build; `tests/test_group17s_seed_definition_authoring.py` (NEW) — 36 tests | **Complete 2026-06-26 — 36 tests pass** | DEF-17S-001/002/003/004/005/006 ✅ |
| Group 17T | Seed Coordinate Map Import and Full-Lap Geometry Alignment: `data/track_seed_coordinate_map.py` (NEW) — `SeedMapStation`, `SeedCoordinateMap`, find/load/export/import/resample; `data/track_map_geometry_alignment.py` (NEW) — `TrackMapGeometryAlignmentResult`, `align_maps_geometry()`, transform estimation, missing-section detection, corner/sector coordinate matching; `ui/track_map_vm.py` — `seed_centreline` defaulted field; `ui/track_model_alignment_vm.py` — `format_geometry_alignment_summary()`, `format_alignment_summary()` accepts `geo_result`; `ui/dashboard.py` — "Geometry match" row, `_tm_refresh_alignment_panel()` computes geometry alignment; `tests/test_group17t_seed_coordinate_map.py` (NEW) — 55 tests | **Complete 2026-06-26 — 55 tests pass** | — |
| Group 17U | Track Library Schema and Seed Data Registry: `data/track_library.py` (NEW) — full dataclass hierarchy + resolver/loader/audit functions; `data/track_library/` directory (NEW) — `index.json`, Daytona track metadata, layout manifest with 12 corners/3 sectors/2 complexes, validation rules, source manifest; `data/track_intelligence.py` — `SeedAuditResult` extended with `seed_source/library_manifest_loaded/validation_rules_loaded`; `ui/track_model_alignment_vm.py` — `"seed_source"` key in `format_alignment_summary()`; `ui/dashboard.py` — "Seed source" row, library-first `resolve_seed_coordinate_map()`; `docs/TRACK_LIBRARY_SCHEMA.md` (NEW); `tests/test_group17u_track_library_schema.py` (NEW) — 83 tests | **Complete 2026-06-26 — 83 tests pass** | — |
| _(Groups 17V–38, A–E, Qualifying Mode, Setup Brain + Strategy Outcome integration)_ | Catalogued in `MASTER_TESTING_REGISTER.md` ("Groups 26–38 + Lettered Groups" and "Integration — Setup Brain + Strategy Outcome") and `docs/CURRENT_CLAUDE_HANDOFF.md`, not re-tabulated here | **Complete — see register** | — |
| Group 18A | Track Truth Library, Calibration Wizard, Station-Based Map Matching Foundation: builds a proper Track Truth spine so the app stops treating curvature-only corners as authoritative (principle: no mapped-corner confidence ⇒ no high-confidence rec). `data/track_truth.py` (NEW) — 4 str-Enums, 8 dataclasses (`TrackStation`/`CornerWindow`/`CornerComplex`/`SectorMarker`/`PitLaneDefinition`/`TrackTruthManifest`/`TrackTruthModel`/`TrackTruthValidationResult`), schema `track_truth_model_v1`+`track_truth_manifest_v1` (runtime-built from existing library manifest+semantic_model — no new file), `resolve_track_truth_model()`, `validate_track_truth_model()` (tiered gates is_accepted → is_usable_for_live_mapping → is_usable_for_ai_corner_context; NO_COORDINATE_GEOMETRY blocker), `can_use_track_truth_for_ai_corner_context()` AI guard; `data/track_truth_matcher.py` (NEW) — `match_track_truth_position()` weighted station scoring scaffold (swappable for HMM/Viterbi), confidence bands mirror `track_map_matching.py`; `data/track_truth_calibration.py` (NEW) — `TrackTruthWizardStage` (8) + `TrackTruthCalibrationWizard`, illegal transitions are no-ops, geometry DELEGATED to Group 17V's `data/track_geometry_builder.build_seed_geometry` (no duplicate algorithm), accept persists via `save_seed_geometry_to_library`; `ui/track_modelling_vm.py` — `format_track_truth_status()` (20-key display dict); `ui/track_modelling_ui.py` — "Track Truth / Mapping" panel + `_tm_refresh_track_truth_panel()`; `tests/test_group18a_track_truth*.py` (NEW ×3) — 45 tests. Daytona stays AI-BLOCKED (no seed_map → zero stations → NO_COORDINATE_GEOMETRY). Setup/Strategy/Live-Engineer rewiring deferred. | **Complete 2026-07-03 — 45 tests pass** | — |
| DEF-17U-UAT-007 | Time Trial calibration laps falsely classified as pit-in / unusable. GT7 has no reliable per-sample pit-lane flag, so geometric pit-in inference false-positived on clean Time Trial laps, and mid-lap start/stop partials poisoned the session median. Fix: pit-in detection DISABLED by default (`build_reference_path(..., pit_detection_enabled=False)`); new `PARTIAL_START` / `PARTIAL_STOP` `CalibrationLapQuality` (first/last lap below 0.5× interior-median path length, ≥ 50 samples, sessions > 2 laps) excluded from the build and not counted as rejected; session median from complete laps only; count-based build diagnostics that never say "pit-in" or "Drive a clean lap first" when pit detection is off. `data/track_calibration.py`, `ui/track_modelling_vm.py`, `ui/track_modelling_ui.py`, `data/track_segment_detection.py`; new `tests/test_def17u_uat007_calibration_build.py` (~35), `tests/test_def17u_uat007_partial_laps.py` (44). | **Complete 2026-07-03 — 4200+ pass (1 pre-existing unrelated failure)** | DEF-17U-UAT-007 ✅ |
| State Consolidation 1 — EventContext | Canonical event/race read model (no feature added, no backend removed, no UI rebuilt). `data/event_context.py` (NEW, pure — `EventContext` immutable dataclass, `EventContextSource`, `EventContextValidationResult`, `build_event_context()` DB-event-first + strategy overlay, `validate_event_context()`, `compute_change_hash()`, `flow_flags()` bridge to `ui/product_flow.py`); `docs/EVENT_CONTEXT_MIGRATION.md` (NEW — all ~35 `config["strategy"]` read sites classified EVENT-CONFIG vs NON-EVENT, migration + StrategyContext/SetupContext plan); `ui/dashboard.py` (`_build_event_context()` helper; `_refresh_telemetry_context()` migrated to read event/car/track from EventContext, DEF-P1-011 preserved); `tests/test_event_context.py` (NEW, 38). `config["strategy"]` retained as legacy compatibility; other ~34 read sites unchanged. | **Complete 2026-07-03 — 4173 pass / 6 skip / 0 fail** | — |
| AI Snapshot Migration — Frozen Context Inputs | Threads frozen, owner-documented snapshots of the four canonical contexts into every migrated AI-input path so prompts receive consistent, non-stale, non-mixed state (no prompt wording changed, no intelligence changed, no legacy store removed). `data/ai_context_snapshot.py` (NEW, pure — `AIContextSnapshot` core with combined `snapshot_id` + four component change markers + CONTEXTS/LEGACY_ONLY/EMPTY source + build/stale warnings; `StrategyAISnapshot` + `PracticeAnalysisSnapshot` frozen race-params preserving each path's exact legacy defaults incl. the DEF-P1-005 practice tuning-absent→LOCKED regime; `SetupAISnapshot` with the build-setup 0.0 refuel/pit-loss defaults; staleness detection strategy-vs-event / setup-vs-event / track-vs-event; LEGACY_ONLY fallback = exact legacy expressions + warning); `docs/AI_SNAPSHOT_MIGRATION.md` (NEW — all 11 AI input paths, owners per input, byte-identity proof, 4 documented intentional differences, deferred deps); `ui/dashboard.py` (`_build_strategy_ai_snapshot`/`_build_practice_ai_snapshot`; migrated `_assemble_strategy_inputs`, `_run_ai_analysis` incl. snapshot `config_id`, `_run_practice_analysis` with snapshot warnings in GT7_AI_DEBUG); `ui/setup_builder_ui.py` (`_build_setup_ai_snapshot`; migrated `_run_build_setup` + frozen worker-thread rec metadata, `_setup_analyse_ai`); `tests/test_ai_context_snapshot.py` (NEW, 41 — verbatim legacy expressions vs snapshots incl. byte-identical `_build_race_prompt` text; snapshot id semantics per context; frozen-after-mutation; staleness; legacy fallback; source scans); 20 legacy source-scan tests updated in place (groups 2/7/10/12a/15/36 — same invariants at the new home). | **Complete 2026-07-03 — 4402 pass / 6 skip / 0 fail** | — |
| Diagnostic Tab Cleanup — Low-Risk UI Dags Removal | Executes the audit's §9 items 1/3/4 — the whole diff is deletions of dead UI, label text and Guide HTML (no logic/prompt/mapping/PTT/voice/persistence/tab-order/fan-out change, pinned by source-scans). DELETED: the 7 hidden, never-`clicked.connect`-ed legacy per-segment review buttons + save-path label + 4 never-applied style strings + the unreachable `_tm_review_confirm/rename/reject/needs_laps/split/merge/save` handlers + `_tm_refresh_review_buttons` + no-op `_tm_refresh_approval_panel` + 8 dead imports (`ui/track_modelling_ui.py`; pure functions in `data/track_segment_review.py` and `ui/track_modelling_vm.get_review_button_states` retained with own coverage); dead never-rendered `_TELEMETRY_REFERENCE_HTML` (~143 lines, `ui/dashboard.py`). RENAMED: "Race Config ID:"→"Session Match Key:" (+plain tooltip; `config_id` mechanics untouched); Diagnostics "Rem(clk):"→"Time left:", "rem_ms(raw):"→"remaining_time_ms:", "Ann queue:"→"Voice queue:" (creation+setText sites); window title + Guide h1 → "Next Gear Racing Pit Crew". GUIDE: phantom "Dashboard" Step 8 → real Home tab; API-key bullet → Strategy Builder field (audit's "Settings duplicate" corrected — no Settings key field exists; relocation deferred); "Tool tabs (⚙)… safe to ignore" note; pip-install tooltip line removed. Deferred: TM jargon glossary, Telemetry raw-row hiding, API-key relocation, both `config["strategy"]` fan-outs (pinned by test). `docs/DIAGNOSTIC_TAB_CLEANUP.md` (NEW); `tests/test_diagnostic_tab_cleanup.py` (NEW, 25); `test_group24` `_tm_` floor 54→46. | **Complete 2026-07-03 — 4479 pass / 6 skip / 0 fail** | — |
| Home Dashboard Build — Race Engineer Command Centre | The missing REQUIREMENTS §12.2 home/next-action surface (audit §1.1), display-only (no race/setup/strategy/track-mapping/AI-prompt/PTT/voice change, no tab reordered/removed, owns no state). `ui/home_dashboard_vm.py` (NEW, pure — `HomeDashboardState`/`HomeDashboardCard`/`HomeDashboardStatus`/`HomeDashboardWarning`/`HomeDashboardNextAction`; `build_home_dashboard_state()` never raises, garbage-safe per section; five cards Race Setup / Track Intelligence / Setup Brain / Strategy Brain / AI Input Safety + Next Best Action from `build_flow_state_summary()`; `build_flow_flags()` context→gate bridge (`has_strategy` requires a stint plan); pure HTML renderers with escaping); `ui/dashboard.py` (Home tab **appended at index 13** — indices 0–12 + `_on_tab_changed` dispatches unchanged, pinned by source-scan; `_build_home_tab`/`_build_home_dashboard_state` (reads the four context builders + `_last_setup_context` + `_build_strategy_ai_snapshot` — pure computation, no AI call)/`_home_has_practice_laps` (read-only DB)/`_home_refresh`/`_home_refresh_if_visible`; hooks at end of `_on_event_set_active` + `_update_race_config`); `ui/setup_builder_ui.py` + `ui/track_modelling_ui.py` (hasattr-guarded refresh hooks); `ui/product_flow.py` ("Home" = workflow role); `docs/HOME_DASHBOARD_BUILD.md` (NEW); `tests/test_home_dashboard_vm.py` (NEW, 52). Deferred: setup-card persistence across restarts, click-to-navigate, SessionContext-owned `has_valid_laps`/`live_active`. | **Complete 2026-07-03 — 4454 pass / 6 skip / 0 fail** | — |
| State Consolidation 4 — TrackContext | Canonical track/layout read model separating track truth from EventContext/StrategyContext/SetupContext, dashboard UI state, seed files, reference paths, station maps and legacy controller state (no track mapping feature added, no UI rebuilt, no persistence format changed, no Daytona accuracy claims). `data/track_context.py` (NEW, pure — `TrackIdentity` (ids/display names/`combined_id` matching `<loc>__<lay>` file conventions), `TrackMapAvailability` (seed metadata/corner windows/coordinate geometry/reference path/calibration laps/station map/reviewed+accepted model/lap offset — flags echo existing audits, never invent accuracy), `TrackGeometryStatus` (modelling status resolver-first, ai_ready, resolver outcome, track-truth gates echoed tri-state), `TrackAlignmentStatus`, `TrackContextSource` (identity priority: TM combos → EventContext → config ids → seed), `TrackContextValidationResult` (identity vs availability vs staleness warnings); helpers `matches_event` tri-state / `mismatches_event` / `is_stale_for_event` / `can_attempt_live_mapping` / `live_mapping_blockers`; `build_track_context()` duck-typed over existing loader results, no file I/O, never raises; `compute_change_hash()` over identity+availability+status; splat-safe `flow_flags()`); `docs/TRACK_CONTEXT_MIGRATION.md` (NEW — 16-item SSOT audit with duplication verdicts, deferred consumers, risks, AI-Snapshot/Home-Dashboard next plan); `ui/track_modelling_ui.py` (`_build_track_context()` helper; `_tm_refresh_track_truth_panel()` identity via TrackContext, combo-sourced only — behaviour-preserving; `_last_track_context` captured); `tests/test_track_context.py` (NEW, 68). Live-map-dot identity, AI id reads, and the Group 17H combo→config fan-out writer intentionally deferred. | **Complete 2026-07-03 — 4361 pass / 6 skip / 0 fail** | — |
| State Consolidation 3 — SetupContext | Canonical setup-recommendation read model that separates setup truth from event truth (EventContext), strategy truth (StrategyContext), and legacy config/DB storage, keyed to `EventContext.change_hash` + `StrategyPromptSnapshot.snapshot_id` so stale setups are detectable (no feature added, no backend removed, no UI rebuilt, no PTT/voice change). `data/setup_context.py` (NEW, pure — `SetupContext` immutable dataclass owning setup_id/config_id/label, `purpose` (QUALIFYING/RACE/PRACTICE/TEST/UNKNOWN via `normalise_purpose`), `source` (AI/GENERATED/MANUAL/SAVED_DB/LEGACY_CONFIG), adjustments (`SetupChangeEntry` round-tripping the AI `changes` shape), changed fields, frozen baseline+target setups, reason/primary_issue/confidence, validation warnings, applied state, `change_hash` + `event_change_hash`/`strategy_snapshot_id`/`telemetry_diagnosis_hash`; keying helpers `matches_event`/`is_stale_for_event`/`is_stale_for_strategy`/`is_missing_identity`/`matches_purpose`; `SetupContextValidationResult` separating setup-input vs staleness warnings; `SetupPromptSnapshot`+`build_setup_prompt_snapshot()` value-copied freeze stable under later config mutation; `build_setup_context()` reads event/strategy only as keys, never raises); `docs/SETUP_CONTEXT_MIGRATION.md` (NEW — every setup store + writers/readers, migrated + deferred consumers, risks, TrackContext/AI-input next plan); `ui/setup_builder_ui.py` (`_build_setup_context()` helper; `_setup_type_prefix()` purpose via SetupContext; `_display_setup_result()` captures `_last_setup_context`); `tests/test_setup_context.py` (NEW, 67). Legacy setup config/DB storage retained; AI setup-prompt + apply/save writers deferred. | **Complete 2026-07-03 — 4293 pass / 6 skip / 0 fail** | — |
| State Consolidation 2 — StrategyContext | Canonical strategy-plan read model that separates strategy state from the event/race config owned by EventContext (no feature added, no backend removed, no UI rebuilt). `data/strategy_context.py` (NEW, pure — `StrategyContext` immutable dataclass owning `config_id`/stint plan/planned stops/pit laps/fuel burn/optional starting-fuel+margin+refuel-required/degradation assumptions/tolerances/`change_hash`/`event_change_hash`; `StintPlanEntry` round-tripping the legacy `stops` shape; `StrategyContextSource` EMPTY/LEGACY_STRATEGY/GENERATED; `StrategyContextValidationResult` separating `strategy_*` from `event_*` warnings; `StrategyPromptSnapshot`+`build_strategy_prompt_snapshot()` value-copied freeze of EventContext race config + StrategyContext plan; `build_strategy_context()` reads event rules from EventContext, ignores event fields in the strategy dict, never raises; `compute_change_hash()` over strategy fields only); `docs/STRATEGY_CONTEXT_MIGRATION.md` (NEW — ownership boundary, every strategy field + writer/readers, migrated + deferred consumers, risks, SetupContext plan); `ui/dashboard.py` (`_build_strategy_context()` helper; `_refresh_lap_bank()` config_id ★ marker migrated); `tests/test_strategy_context.py` (NEW, 53). `config["strategy"]` retained as legacy compatibility; AI-input path deferred. | **Complete 2026-07-03 — 4226 pass / 6 skip / 0 fail** | — |
| Product Consolidation Sprint | Audit + safe first-pass UI clean-up (no feature added, no backend removed, no tab reordered). `docs/PRODUCT_CONSOLIDATION_AUDIT.md` (NEW — per-tab KEEP/MOVE/RENAME/MERGE/DELETE/HIDE verdicts, 14-item single-source-of-truth table + ranked violations, 9-context target architecture, next-sprint plan); `ui/product_flow.py` (NEW, pure — tab roles, 13-step journey, `build_flow_state_summary()` next-action logic, tab-title decoration); `ui/dashboard.py` ("Debug"→"Diagnostics" tab, `_apply_product_flow_tab_markers()` ⚙ marks Telemetry/Diagnostics/AI Log/Track Modelling); `ui/track_modelling_ui.py` ("5. Track Model Alignment"→"5. Seed Geometry", "Resolver Status"→"Track Model Status"); `tests/test_consolidation_product_flow.py` (NEW, 27), `tests/test_group23b_ui_cleanup.py` (updated). Deferred SSOT refactors (event fan-out, track/layout split, setups dual-residence) documented, not started. | **Complete 2026-07-03 — 4135 pass / 6 skip / 0 fail** | — |

---

## Root Causes Identified (Post-UAT)

| ID | Name | Status | Cascades To |
|----|------|--------|-------------|
| Root Cause A | Event persistence/reload broken | **Fixed (Group 7)** | DEF-P1-009, DEF-P1-005, tyre wear, fuel mult, avail/req tyres |
| Root Cause B | Session reload mapping incomplete | **Fixed (Group 8)** | DEF-P2-013, DEF-P2-014, DEF-P2-009 |
| Root Cause C | AI Debug/Log view not visible | **Fixed (Group 9)** | DEF-P1-010 — unblocks DEF-P4-002, DEF-P2-007, DEF-P2-016 verification |
| Root Cause D | AI prompt not using Event BoP/tuning | **Verified by Group 10 tests** | DEF-P1-005 — runtime retest via AWR-031/AWR-032/AWR-037/AWR-038 |

---

## Defect Summary

### Open Defects (implementation required)

| ID | Priority | Title | Group |
|----|----------|-------|-------|
| DEF-P2-018 | P2 | Outlap row has no visual identification in Practice Review | Group 15 |
| DEF-P3-005 | P3 | Pit window is static, not recalculated on deviation | Deferred |
| DEF-P3-007 | P3 | Disabled race type field not visually dimmed | Group 15 |
| DEF-P3-008 | P3 | Top speed target never populated from valid practice telemetry | Group 15 |
| ~~DEF-P3-013~~ | — | ~~AILogEntry missing car_id/track~~ | Fixed Group 15A |

### Awaiting Retest (fix complete, runtime verification needed)

| ID | Priority | Title | AWR |
|----|----------|-------|-----|
| DEF-P1-001 | P1 | Session opens on mode selection | AWR-001 |
| DEF-P1-002 | P1 | Outlap recording | AWR-002/003 |
| DEF-P1-003 | P1 | Save Session crash | AWR-004/005 |
| DEF-P1-004 | P1 | Timed race in AI prompt | AWR-006 |
| DEF-P1-005 | P1 | AI prompt BoP/tuning restrictions | AWR-031/AWR-032/**AWR-042** |
| DEF-P1-006 | P1 | Compound lap counts in AI | AWR-013 |
| DEF-P1-007 | P1 | Fuel burn single source | AWR-014 |
| DEF-P1-008 | P1 | Practice RACE_FINISHED guard | AWR-011 |
| DEF-P1-009 | P1 | Event load restores saved variables | **AWR-031** |
| DEF-P1-010 | P1 | AI Debug / AI Log tab not visible | **AWR-036** |
| DEF-P1-005 | P1 | BoP On + Tuning Off prompt contains locked block | **AWR-037** |
| DEF-P1-005 | P1 | Partial tuning — locked fields not sent as editable | **AWR-038** |
| DEF-P2-016 | P2 | Practice Analysis blocks AI call on bad input data | **AWR-039** |
| DEF-P1-011 | P1 | Fuel Burn Auto shows stale value after event switch | **AWR-040** |
| DEF-P2-021 | P2 | AI Log list auto-select + timestamp + status format | AWR-041/**AWR-044** |
| DEF-P2-023 | P2 | No-refuel pit stop detected as pit lap | **AWR-045** |
| DEF-P2-024 | P2 | Outlap metadata (is_out_lap) persists after Save Session + reload | **AWR-046** |
| DEF-P2-025 | P2 | Fuel Start/End preserved after Save Session + reload | **AWR-047** |
| DEF-P2-019 | P2 | Compound propagation stops at pit lap boundary | **AWR-048** |
| DEF-P2-020 | P2 | Live tyre shows race plan/setup compound, not mandatory tyre | **AWR-049** |
| DEF-P1-012 | P1 | BoP practice prompt provides setup changes when tuning locked | **AWR-050** |
| DEF-P2-029 | P2 | Outlap metadata dropped when write_lap stats=None | **AWR-051** |
| DEF-P2-030 | P2 | Save Session creates duplicate session when live session open | **AWR-052** |
| DEF-P2-031 | P2 | Qualifying outlap calming phrase never fires | **AWR-053** |
| DEF-P2-032 | P2 | Pit/fuel alerts suppressed in qualifying (regression guard) | **AWR-054** |
| DEF-P2-033 | P2 | AI Log auto-select fires on hidden widget | **AWR-055** |
| DEF-P2-034 | P2 | AI Log timestamps in UTC instead of local time | **AWR-056** |
| DEF-P2-035 | P2 | Garage shows no DB setups; exceptions swallowed | **AWR-057** |
| DEF-P1-013 | P1 | Strategy race_params missing race_type/tuning/bop/avail_tyres | **AWR-058 CLOSED** |
| DEF-P1-014 | P1 | Practice worker car_id=0 + new DB connection | **AWR-059 CLOSED** |
| DEF-P2-038 | P2 | Practice race_params missing bop | **AWR-060 CLOSED** |
| DEF-P2-039 | P2 | avail_tyres missing from race_params and prompts | **AWR-061 CLOSED** |
| DEF-P2-040 | P2 | Driver feedback not in Practice AI prompt | **AWR-062 CLOSED** |
| DEF-P2-041 | P2 | Prev AI recs not in Practice AI prompt | **AWR-063 PARTIAL — DEF-P3-013** |
| DEF-P2-036 | P2 | PTT coaching missing car_name/car_specs/compound | **AWR-064 CLOSED** |
| DEF-P2-037 | P2 | PTT setup_advice reads stale config setup | **AWR-065 CLOSED** |
| DEF-P3-009 | P3 | Race prompt hardcodes laps for timed race | **AWR-066 CLOSED** |
| DEF-P3-010 | P3 | build_car_setup missing race context params | **AWR-067 CLOSED** |
| DEF-P3-011 | P3 | _DATA_QUALITY_NOTE absent from ai_planner prompts | **AWR-068 CLOSED** |
| DEF-P3-012 | P3 | Strategy results not validated for tuning violations | **AWR-069 CLOSED** |
| DEF-P3-013 | P3 | AILogEntry missing car_id/track — get_recent_ai_recommendations() always returns empty | **OPEN — raised 2026-06-23** |
| DEF-P2-013 | P2 | Pit flag persists after History reload (post-Group-8 sessions) | AWR-033/**AWR-043** |
| DEF-P2-014 | P2 | Fuel start/end preserved after reload (post-Group-8 sessions) | AWR-035/**AWR-043** |
| DEF-P2-009 | P2 | Fuel Burn Auto updates on History reload | **AWR-034** |
| DEF-P2-003 | P2 | Required tyres checkbox grid | AWR-016 |
| DEF-P2-007 | P2 | AI setup restriction banner | AWR-022 |
| DEF-P2-010 | P2 | Driver feedback in Practice Review | AWR-030 |
| DEF-P2-011 | P2 | Outlap excluded from best-lap calc | AWR-008 |
| DEF-P2-012 | P2 | Tyre wear in AI prompt | AWR-015 |
| DEF-P2-015 | P2 | Top speed 11 km/h artefact guard | AWR-029 |
| DEF-P2-016 | P2 | Practice Analysis validation gate | AWR-023 |
| DEF-P2-017 | P2 | Qualifying RACE_FINISHED guard | AWR-024 |
| DEF-P3-001 | P3 | Brake balance step = 1 | AWR-009 |
| DEF-P3-002 | P3 | Live tyre compound label | AWR-010 |
| DEF-P3-003 | P3 | New lap inherits compound from previous | AWR-012 |
| DEF-P3-004 | P3 | Race type mutual exclusivity | AWR-025 |
| DEF-P3-006 | P3 | Session summary recalculates after reload | AWR-028 |
| DEF-P4-001 | P4 | PTT on Live tab | AWR-007 |
| DEF-P4-002 | P4 | AI model is claude-opus-4-8 | AWR-019 |
| DEF-P4-003 | P4 | Fuel formula percentage multiplier | AWR-020 |

### User Verified (UAT passed)

DEF-P1-001 (partial), DEF-P1-003 ✅, DEF-P1-004 ✅, DEF-P1-007 (in-session only), DEF-P1-008 ✅,
DEF-P2-001 ✅, DEF-P2-002 ✅, DEF-P2-004 ✅, DEF-P2-006 ✅, DEF-P2-008 ✅, DEF-P2-010 ✅,
DEF-P2-012 ✅, DEF-P2-QRF ✅, DEF-P3-001 ✅, DEF-P3-006 (partial), DEF-P4-001 ✅, DEF-P4-003 ✅,
DEF-P1-006 ✅

---

## Group 12 — What Was Fixed (2026-06-22)

### 12a — DEF-P1-005: BoP/tuning default bug

**Root cause confirmed:** `_run_practice_analysis()` line 3183 used `_psc.get("tuning", True)`. When the "tuning" key was absent from `config["strategy"]` (old config, or silent exception in `_on_event_set_active()` before write), this default returned `True`, making `tuning_locked = not bool(True) = False`. Practice analysis ran with full setup regardless of event configuration.

**Fix 1 — `_run_practice_analysis()` line 3183:** `_psc.get("tuning", True)` → `_psc.get("tuning", False)`. Absent key now produces `tuning_locked = True` (locked = safe default).

**Fix 2 — `_on_event_set_active()` except block:** `except Exception: pass` → `except Exception: import traceback; traceback.print_exc()`. Previously silently swallowed all failures including the TypeError that prevented `strat["tuning"]` from being written.

**Fix 3 — Debug context print:** When `GT7_AI_DEBUG=1` is set, prints `bop`, `tuning` (raw value), `tuning_locked`, `allowed_tuning`, `race_type`, `fuel_mult`, `tyre_wear` to stdout immediately after `race_params` is built.

### 12b — DEF-P2-022/013/014: Investigation (no code change)

**Conclusion:** Root cause hypothesis (different data sources) was **incorrect**. Both `_on_history_load_session()` and `_import_bank_session()` call the same `get_session_laps()` which correctly SELECTs `fuel_start`, `fuel_end`, `is_pit_lap`, `is_out_lap`. Both correctly pass all fields to `_add_bank_lap_row()`. `write_lap()` in `main.py` correctly writes them from `LapRecord`. The History detail panel only shows `fuel_used` (not `fuel_start`/`fuel_end`) — the user's comparison was between different columns. Zero values in AWR-040 were pre-Group-8 session data. DEF-P2-022 closed. DEF-P2-013/014 awaiting retest with a post-Group-8 session.

### 12c — DEF-P2-021: Three remaining AI Log display issues

**Fix 1 — Timestamp:** `entry.timestamp[11:19]` (showed HH:MM:SS only) → `entry.timestamp[:19].replace("T", " ")` (shows YYYY-MM-DD HH:MM:SS).

**Fix 2 — Status text:** `"✓"/"✗"` → `"✓ OK"/"✗ FAIL"/"⊘ DRY-RUN"`. Dry-run detected when `duration_ms == 0 and entry.error_msg and "AI_DEBUG" in entry.error_msg`.

**Fix 3 — Deferred auto-select:** `_on_ai_log_entry()` now sets `self._ai_log_pending_select = True`. New `_flush_ai_log_pending_select()` helper calls `setCurrentRow(count - 1)` and clears the flag. `_on_tab_changed()` now handles index 11 (AI Log tab) by calling `_flush_ai_log_pending_select()` — ensures selection is applied when the tab becomes visible, not when the hidden widget received `setCurrentRow()`.

### Tests Added

- **`tests/test_group12a_bop_tuning_propagation.py`** — 12 tests in 4 classes
- **`tests/test_group12b_history_practice_mapping.py`** — 20 tests in 5 classes
- **`tests/test_group12c_ai_log_display.py`** — 12 tests in 3 classes

---

## Group 11 — What Was Fixed (2026-06-22)

### DEF-P1-011 — Fuel Burn Auto stale label after event switch

**Problem:** `_on_event_set_active()` calls `_sync_setup_builder_from_event()` which only updates `_lbl_fuel_burn_display` when `tracker.avg_fuel_per_lap > 0`. With no live telemetry the label was left showing `config["strategy"]["fuel_burn_per_lap"]` from a previous session (e.g. `"3.00 L/lap (last session)"`). The number coincidentally matched the event fuel multiplier (both 3×), causing confusion.

**Fix — `ui/dashboard.py` `_on_event_set_active()`:** Added reset block after `_sync_setup_builder_from_event()`. When `tracker.avg_fuel_per_lap <= 0 AND _loaded_session_avg_fuel <= 0`, resets `_lbl_fuel_burn_display` to `"— (complete practice laps to calibrate)"`. Live telemetry and loaded-session paths unchanged.

### DEF-P2-021 — AI Log list didn't auto-select new live entries

**Problem:** `_add_ai_log_list_item()` called `scrollToBottom()` after appending the new item. `bridge.ai_log_entry` uses QueuedConnection (cross-thread), so the slot fires after the timer tick — at which point the AI Log tab may not be the active tab and `scrollToBottom()` has no effect. Navigating to the tab showed the DB-loaded history at the top; the new entry at the bottom was not selected or visible. The user clicked an old DB-loaded entry and saw the Prompt sub-tab from that entry — explaining "Prompt tab populated. Prompt text visible" with "No visible AI log entry."

**Fix — `ui/dashboard.py`:**
- `_add_ai_log_list_item()` gains `auto_select: bool = False`. When `True`, calls `setCurrentRow(count - 1)` after `addItem()`.
- `_on_ai_log_entry()` (live signal handler) passes `auto_select=True`.
- `_on_ai_log_entry_dict()` (DB startup load) uses default `auto_select=False`.

### Tests Added
**`tests/test_group11_ui_display_fixes.py`** — 8 new tests in 2 classes.

---

## Group 9 — What Was Fixed (2026-06-22)

### Problem
`call_api()` in `strategy/_ai_client.py` raised `RuntimeError` in the `if _AI_DEBUG:` branch before reaching the `try/except` block that contains both `_fire_log_hook()` calls. The signal chain (`_ai_log_callback` → `bridge.ai_log_entry.emit()` → `dashboard._on_ai_log_entry()`) was fully wired and correct — but the entry was never created because the hook was never called.

When the user tested AI features with `GT7_AI_DEBUG=1` (as the test plan required), every intercepted AI call printed the prompt to stdout and then raised RuntimeError — leaving the AI Log tab permanently empty.

### Fix (1 file changed)

**`strategy/_ai_client.py` — `call_api()` debug branch:**
Added `_fire_log_hook(AILogEntry(...))` immediately before the `raise RuntimeError`. The dry-run entry captures:
- `success=False`
- `response="[AI_DEBUG dry-run — no API call made]"`
- `error_msg="AI_DEBUG mode active — prompt intercepted, no API call made"`
- `feature`, `model`, `prompt` from the actual call arguments
- `duration_ms=0`, `prompt_tokens=0`, `response_tokens=0`, `estimated_cost=0.0`

The entry is written to DB via the existing `_ai_log_callback` in `main.py` and emitted on the bridge signal. No other files required changes.

### Tests Added
**`tests/test_group9_ai_log.py`** — 18 new tests in 3 classes:
- `TestCallApiDebugFiresLogHook` (9 tests): Source-scan of `call_api()` confirming `_fire_log_hook` is called inside the `_AI_DEBUG` block, appears before `raise RuntimeError`, passes `success=False`, non-empty `error_msg`, `feature`, `model`, `prompt`. Also confirms success and failure paths in the real API call block both fire the hook.
- `TestDashboardAiLogWiring` (4 tests): Source-scan confirming `_connect_signals()` connects `ai_log_entry` signal, `_build_ai_log_tab()` loads DB history on startup, `_on_ai_log_entry` appends to list and calls `_add_ai_log_list_item`.
- `TestAiInteractionsDbRoundTrip` (5 tests): DB round-trip for `log_ai_interaction()` and `get_ai_interactions()` — confirms all fields survive the write/read cycle, failed entries (success=0) are stored correctly, results return newest-first, limit is respected.

---

## Group 8 — What Was Fixed (2026-06-22)

### Problem
`main.py` EventDispatcher called `write_lap()` without passing `is_pit_lap`, `is_out_lap`, `delta_ms`, or `session_type` from the `LapRecord`. These four parameters defaulted to 0/False/"" in the `write_lap()` signature. So the DB always stored `is_pit_lap = 0` and `is_out_lap = 0` regardless of what the telemetry actually recorded. The live Practice Review display reads from the `LapRecord` object in memory (correct), but after a History reload the display reads from the DB (always 0 → pit flag missing, outlaps included in fuel average).

Separately, after `_on_history_load_session()` computed `_loaded_session_avg_fuel`, the Strategy Builder `_lbl_fuel_burn_display` label was never refreshed — it still showed the value from app startup.

### Fix (2 files changed)

**`main.py` — `EventDispatcher._dispatch()` lines ~224–236:**
Added four missing fields to the `write_lap()` call:
- `is_pit_lap=bool(getattr(record, "is_pit_lap", False))`
- `is_out_lap=bool(getattr(record, "is_out_lap", False))`
- `delta_ms=int(getattr(record, "delta_ms", 0))`
- `session_type=(record.session_type.value if hasattr(record.session_type, "value") else str(...))`

**`ui/dashboard.py` — `_on_history_load_session()` and `_import_bank_session()`:**
Added fuel burn display refresh immediately after `_loaded_session_avg_fuel` is computed:
```python
if hasattr(self, "_lbl_fuel_burn_display") and self._loaded_session_avg_fuel > 0:
    self._lbl_fuel_burn_display.setText(
        f"{self._loaded_session_avg_fuel:.2f} L/lap (loaded session)")
```

No DB schema changes. No `session_db.py` changes.

### Tests Added
**`tests/test_group8_session_reload.py`** — 37 new tests in 4 classes:
- `TestGetSessionLapsColumns` (13 tests): DB round-trip for `is_pit_lap`, `is_out_lap`, `fuel_start`, `fuel_end`. Confirms pit flag survives write_lap → get_session_laps. Confirms fuel average excludes pit laps and outlaps.
- `TestMainWriteLapPassesPitFlag` (6 tests): Source-scan confirming `main.py` write_lap call includes `is_pit_lap`, `is_out_lap`, `fuel_start`, `fuel_end`, `delta_ms`, `session_type`.
- `TestHistoryLoadSessionMapping` (7 tests): Source-scan confirming `_on_history_load_session` passes pit/fuel fields and updates `_lbl_fuel_burn_display`.
- `TestImportBankSessionMapping` (5 tests): Source-scan confirming `_import_bank_session` does the same.
- `TestAddBankLapRowRendering` (6 tests): Source-scan confirming `_add_bank_lap_row` renders pit flag, fuel columns, and background colours correctly.

---

## Group 7 — What Was Fixed (2026-06-22)

### Problem
`_on_event_selected()` in `ui/dashboard.py` silently failed when populating form fields from the DB. The `tyre_wear`, `fuel_mult`, and `refuel_rate_lps` columns are `REAL` in SQLite, which SQLite's Python driver returns as Python `float`. The form widgets `_evt_tyre_wear`, `_evt_fuel_mult`, `_evt_refuel_rate` are `QSpinBox` (integer-only). PyQt6's `QSpinBox.setValue(float)` raises `TypeError`. The method's `except Exception: pass` swallowed this, leaving the spinboxes at 1 (the default minimum) and skipping all subsequent field population — fuel_mult, avail_tyres, req_tyres, tuning categories, and notes never loaded.

### Fix (1 file changed)
**`ui/dashboard.py` — `_on_event_selected()` lines ~7321–7331, ~7354–7359:**

1. `int(round(...))` cast applied to `tyre_wear`, `fuel_mult`, and `refuel_rate_lps` before `setValue()`.
2. `except Exception: pass` replaced with `except Exception: import traceback; traceback.print_exc()`.
3. Tuning permissions group visibility changed from `_bop_on and _tun_on` to `bool(_tun_on)`.

No DB schema changes. No `session_db.py` changes. No other files changed.

### Tests Added
**`tests/test_group7_event_persistence.py`** — 28 new tests in 4 classes:
- `TestEventDBRoundTrip` (15 tests): DB round-trip for all Group 7 fields via `upsert_event` + `get_all_events`. Documents that `tyre_wear` and `fuel_mult` return as Python `float` from DB.
- `TestEventSelectedFixApplied` (7 tests): Source-scan confirming `int(round(...))` is in `_on_event_selected`, exception handler prints traceback, tuning perms uses `bool(_tun_on)`.
- `TestEventSetActiveStratKeys` (7 tests): Source-scan confirming `_on_event_set_active` writes all required strategy keys.
- `TestPracticeAnalysisBoPContext` (2 tests): Source-scan confirming `_run_practice_analysis` passes `tuning_locked` and `allowed_tuning` to `race_params` (DEF-P1-005 auto-resolution path).

---

## Pending Implementation (Groups 8–11)

### Group 8 — Session Reload Mapping — COMPLETE (2026-06-22)
**Target:** DEF-P2-013 (pit flag lost), DEF-P2-014 (fuel start/end lost), DEF-P2-009 (stale fuel burn)
**Status:** Fixed — AWR-033, AWR-034, AWR-035 awaiting runtime verification

### Group 9 — AI Debug / Log Visibility — COMPLETE (2026-06-22)
**Target:** DEF-P1-010
**Status:** Fixed — AWR-036 awaiting runtime verification
**Fix:** `_fire_log_hook()` now called in `_AI_DEBUG` branch of `call_api()` before `raise RuntimeError`. Dry-run entries appear in AI Log tab with `success=False` and full prompt captured.

### Group 10 — AI Prompt BoP Context (P1)
**Target:** DEF-P1-005 runtime verification
**Dependency:** Group 7 runtime retest (AWR-031/AWR-032) must pass first.
**Note:** Code is already correct (`_run_practice_analysis` passes `tuning_locked` / `allowed_tuning`). May auto-resolve. Only needs code changes if AWR-032 shows the prompt is still missing the restriction block after Group 7 fix.

### Group 11 — Visual / UX Fixes (P2–P3)
**Target:** DEF-P2-018, DEF-P2-019, DEF-P2-020, DEF-P3-007, DEF-P3-008
**Files:** `ui/dashboard.py`
**Do not start until Groups 8–10 complete.**

---

## Key Files

| File | Role |
|------|------|
| `ui/dashboard.py` | Main UI — ~7700 lines — all Event Planner, Practice Review, Setup Builder, Live tab logic |
| `data/session_db.py` | SQLite persistence — events, laps, sessions, AI interactions, setups |
| `strategy/ai_planner.py` | Practice Analysis AI — `RaceParams`, `analyse_practice_session`, prompt builder |
| `strategy/driving_advisor.py` | PTT coaching AI — `DrivingAdvisor`, prompt builders |
| `strategy/_ai_client.py` | Anthropic API wrapper — `call_api`, `ai_interactions` table write |
| `telemetry/state.py` | `RaceStateTracker` — lap detection, session type, oversteer/kerb detection |
| `telemetry/recorder.py` | `LapTelemetryRecorder` — per-frame stats, `LapStats`, `TelemetryFrame` |
| `voice/announcer.py` | TTS engine — `VoiceAnnouncer`, session mode guard on pit/fuel alerts |
| `voice/query_listener.py` | PTT + speech-to-text — `QueryListener`, intent keywords |
| `data/tyres.py` | Tyre compound catalogue — `ALL_COMPOUNDS`, `normalise_code`, `get_by_code` |

---

## Dev Notes

- **No Qt in tests.** All tests use source-code scanning (`_method_body()` pattern) or in-memory `SessionDB(":memory:")`. Do not add `QApplication` to tests.
- **DB is authoritative for events.** Config.json still syncs as a fallback but DB is the primary store.
- **`isolation_level=None`** on the SQLite connection means autocommit — no explicit `commit()` needed.
- **Python 3.14 / PyQt6.** QSpinBox.setValue() enforces `int` strictly in PyQt6. DB `REAL` columns return Python `float`. Always cast before passing to QSpinBox.
- **`GT7_AI_DEBUG=1`** must be set as an env var before the Python process starts. In PowerShell: `$env:GT7_AI_DEBUG=1; python main.py`. In cmd: `set GT7_AI_DEBUG=1 && python main.py`.
