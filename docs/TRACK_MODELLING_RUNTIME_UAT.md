# Track Modelling — Runtime UAT Checklist

**Group:** 17M — Runtime UAT and Calibration Workflow Hardening  
**Purpose:** Step-by-step manual UAT procedure to verify the full track modelling workflow from GT7 connection to live segment resolution.

---

## Preconditions

| # | Item | Pass / Fail |
|---|------|-------------|
| P1 | GT7 is running and the target track is loaded | |
| P2 | GT7 Custom UDP telemetry is enabled in GT7 settings and pointing at this machine's IP on port 33740 | |
| P3 | Seed data (`data/track_models/seed_tracks.json`) is present and includes the target track | |
| P4 | The Track Modelling tab is visible in the dashboard | |
| P5 | `python -m pytest tests/` passes (all unit tests green before starting UAT) | |

---

## 1. Track and Layout Selection

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 1.1 | Open the Track Modelling tab | Panel displays Location and Layout dropdowns | | |
| 1.2 | Select a Track Location from the Location combo | Layout combo populates with layouts for that location | | |
| 1.3 | Select a specific Layout | Seed data info appears in the Calibration Car label or seed status area | | |
| 1.4 | Verify the seed status label shows the track's known length (from seed) | Track length in metres displayed (e.g. "5807 m") | | |
| 1.5 | Switch to a different Location | Layout combo resets and repopulates for the new location | | |

**Defects found:**

---

## 2. Calibration Car Visibility

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 2.1 | With track selected, observe "Calibration Car" note label | Label shows the Calibration Car boundary note (from CALIBRATION_CAR_BOUNDARY_NOTE) | | |
| 2.2 | Verify it references a Gr.4 or similar stable reference car | Note text is present and readable, warns against seed-only coaching | | |

**Defects found:**

---

## 3. GT7 Connection and Packet Reception

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 3.1 | Ensure GT7 is on a menu screen (not in-race) | Packet age label shows "No packets received" | | |
| 3.2 | Start a driving session in GT7 (practice or time trial on the selected track) | Packet age label refreshes to "Last packet: N ms ago" in green | | |
| 3.3 | Wait 15 seconds without GT7 packets (pause game or switch to menu) | Packet age label changes colour to amber/red and shows "check connection" text | | |
| 3.4 | Resume driving | Packet age returns to green | | |

**Defects found:**

---

## 4. Recording State: Start

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 4.1 | With track selected and GT7 packets arriving, click "Start Calibration" | Button becomes disabled; Stop button becomes enabled; state label shows "Recording" | | |
| 4.2 | Verify the recording indicator shows "● RECORDING" | REC indicator visible in status area | | |
| 4.3 | Attempt to click "Start Calibration" again (should be disabled) | Button disabled; no double-start | | |
| 4.4 | Observe Sample Count label incrementing | Label shows "Samples: N \| Lap: M" with N increasing each packet burst | | |

**Defects found:**

---

## 5. Lap Count During Recording

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 5.1 | Complete one full lap in GT7 | Lap count in status increments from 0 to 1 | | |
| 5.2 | Complete a second lap | Lap count shows 2 | | |
| 5.3 | Complete a third lap | Lap count shows 3; Build button may become enabled (requires ≥1 usable lap) | | |
| 5.4 | Note whether any laps are rejected (invalid laps) | Rejected count shown separately from usable count if applicable | | |

**Defects found:**

---

## 6. Stop Recording

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 6.1 | Click "Stop Calibration" after completing at least 2 laps | Stop button disables; Start button re-enables; state changes to "Stopped" | | |
| 6.2 | Verify sample count is preserved after stopping | Sample count label still shows last value | | |
| 6.3 | Verify "Build Reference Path" button is now enabled | Button enabled (requires stopped state + ≥1 usable lap) | | |

**Defects found:**

---

## 7. Reference Path Build and Save

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 7.1 | Click "Build Reference Path" | Progress or status update; state transitions to "Built" | | |
| 7.2 | Verify state label shows "Built" with point count and confidence | e.g. "Path built: 412 pts, conf 0.94" | | |
| 7.3 | Verify "Save Reference Path" button is now enabled | Button enabled | | |
| 7.4 | Click "Save Reference Path" | File saved to `data/track_models/<loc>__<lay>.json`; saved path label updates | | |
| 7.5 | Verify saved path label shows the file path | Full path visible in the status label | | |
| 7.6 | Verify "Detect Segments" button is now enabled | Button enabled after successful save | | |

**Defects found:**

---

## 8. Segment Detection

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 8.1 | Click "Detect Segments" | Segment detection runs; segment table populates with detected segments | | |
| 8.2 | Verify at least one segment appears in the table | At minimum one row (e.g. "Straight 1") | | |
| 8.3 | Verify each row shows segment name, type, start/end distance | Columns populated | | |
| 8.4 | Select a segment row | Row highlights; Confirm/Rename/Reject buttons become enabled | | |

**Defects found:**

---

## 9. Segment Review Workflow

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 9.1 | Select a segment and click "Confirm" | Segment status updates to "confirmed" in table | | |
| 9.2 | Select a segment and click "Rename" | Dialog or inline editor opens for name input | | |
| 9.3 | Select a segment and click "Reject" | Segment marked as rejected | | |
| 9.4 | Click "Needs More Laps" on an uncertain segment | Segment flagged appropriately | | |
| 9.5 | Verify "Save Reviewed Model" button enables after reviewing segments | Button enabled | | |
| 9.6 | Click "Save Reviewed Model" | Reviewed model saved to `data/track_models/<loc>__<lay>__reviewed.json`; reviewed model path label updates | | |
| 9.7 | Verify reviewed model path label shows the saved path | Full path visible | | |

**Defects found:**

---

## 10. Lap Offset Calibration

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 10.1 | With track selected and seed or reference path available, observe "Create Zero Offset" button state | Button enabled (requires track + track_length_m) | | |
| 10.2 | Click "Create Zero Offset" | Zero-offset calibration created; Offset status label updates to show "Provisional — 0.0 m" | | |
| 10.3 | Verify provisional note is shown | Warning note visible: "Zero-offset is provisional..." | | |
| 10.4 | Verify confidence shown as LOW | Confidence label shows LOW | | |
| 10.5 | Verify offset source shows "zero_offset" | Source label shows "zero_offset" | | |
| 10.6 | Click "Save Offset" | Offset JSON saved to `data/track_models/<loc>__<lay>__lap_offset.json` | | |
| 10.7 | Restart the application and re-select the same track | "Load Offset" button is available | | |
| 10.8 | Click "Load Offset" | Previously saved calibration loads; status label restores | | |
| 10.9 | Verify status correctly reflects loaded calibration (provisional vs validated) | Status label accurate | | |
| 10.10 | Select a different track (no offset file) and click "Load Offset" | UI shows "No saved offset calibration found" message; does not crash | | |

**Defects found:**

---

## 11. Resolver Status

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 11.1 | With reviewed model saved, observe Resolver Status panel | Resolver status shows "reviewed_model" source type | | |
| 11.2 | Verify AI-ready field shows Yes/No based on model completeness | AI-ready: Yes (if segments confirmed and path complete) | | |
| 11.3 | Delete the reviewed model file and reload the track | Resolver falls back to seed_only; status shows "seed_only" | | |
| 11.4 | With no seed or model, verify resolver status shows "missing" | Status shows "missing" or "none" | | |

**Defects found:**

---

## 12. Lap Offset Status in Resolver Summary

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 12.1 | With zero-offset created, observe the live resolver status summary | Summary shows "Offset: provisional (0.0 m)" | | |
| 12.2 | Verify track length shown in resolver summary | Summary shows track length in metres | | |
| 12.3 | With no offset, verify summary shows "Offset: none" | Summary text reads "none" or "unavailable" | | |

**Defects found:**

---

## 13. Live Segment Resolution

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 13.1 | With reviewed model and offset calibration loaded, enter a live driving session in GT7 on the same track | Live segment resolver activates; segment resolution status shown | | |
| 13.2 | Drive through a corner with a confirmed segment | Resolver status shows segment name (e.g. "T1 Braking Zone") and status "matched" | | |
| 13.3 | Drive a long straight with no special segment | Status shows "unresolved" or nearest segment name | | |
| 13.4 | Verify road_distance is available | Resolver status shows road distance in metres | | |
| 13.5 | Switch to a track with no reviewed model | Live segment resolver falls back to seed; coaching cues note "seed-only" limitation | | |

**Defects found:**

---

## 14. Coaching Cue Status

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 14.1 | With live segment resolution active, observe whether coaching cues fire | Coaching cue events generated for segments with timing data | | |
| 14.2 | With seed-only model, verify coaching cues are appropriately limited | No detailed position cues without reviewed model | | |
| 14.3 | With no offset calibration, verify any road_distance-to-lap_distance mapping warnings are surfaced | Warning or note in resolver summary if offset is missing | | |

**Defects found:**

---

## 15. Error States

| # | Step | Expected | Pass / Fail | Notes |
|---|------|----------|-------------|-------|
| 15.1 | Click "Build Reference Path" without any recorded laps | Build button disabled; cannot be triggered | | |
| 15.2 | Click "Create Zero Offset" with no track selected | Button disabled; no crash | | |
| 15.3 | Click "Create Zero Offset" when track length is unknown | Warning dialog shown; does not create invalid calibration | | |
| 15.4 | Attempt to load offset when none exists for this track | Informational dialog shown; does not crash | | |
| 15.5 | Kill GT7 mid-recording (simulate packet loss) | Packet age label goes red; recording continues accumulating; Stop button remains enabled | | |
| 15.6 | Build path with only one partial lap of data | Build may succeed with low confidence, or return an error; no crash | | |

**Defects found:**

---

## Pass / Fail Summary

| Section | Pass | Fail | Notes |
|---------|------|------|-------|
| 1. Track / Layout Selection | | | |
| 2. Calibration Car | | | |
| 3. GT7 Connection | | | |
| 4. Recording Start | | | |
| 5. Lap Count | | | |
| 6. Stop Recording | | | |
| 7. Build and Save Path | | | |
| 8. Segment Detection | | | |
| 9. Segment Review | | | |
| 10. Lap Offset Calibration | | | |
| 11. Resolver Status | | | |
| 12. Offset in Resolver Summary | | | |
| 13. Live Segment Resolution | | | |
| 14. Coaching Cue Status | | | |
| 15. Error States | | | |
| **OVERALL** | | | |

---

## Tester Notes

**Tester:** ____________________________  
**Date:** ____________________________  
**GT7 Version:** ____________________________  
**Dashboard Build:** ____________________________  

Free text for observations, reproduction steps for defects, or follow-up items:

```
[Enter notes here]
```

---

## UAT Defect Register (2026-06-25 Daytona Road Course Run)

### DEF-17M-UAT-001 — Lap Count Mismatch Display
**Reported:** 2026-06-25  
**Status:** FIXED (Group 17M UAT Remediation)  
**Symptom:** UI showed "8 laps done / 5 valid" — user drove 5 complete laps. Confusing because no explanation of the 3 extra counted segments.  
**Root cause:** `lap_count = len(session.laps)` counts ALL closed lap segments including partial fragments at session start/end. Quality assessment (usable/rejected) only populates after `build_reference_path()`.  
**Fix:** `format_lap_count_info()` in `track_modelling_vm.py` produces three display strings:
  - `captured_text`: raw count with state-aware context ("8 lap segments captured")
  - `quality_text`: quality breakdown after build ("5 usable / 3 rejected / 0 low-confidence")
  - `explanation`: tooltip explaining gap between captured and assessed counts
`_tm_update_cal_status()` uses these strings; `_tm_lbl_lap_info` tooltip shows the explanation.

---

### DEF-17M-UAT-002 — Detect Segments Crashes App
**Reported:** 2026-06-25  
**Status:** FIXED (Group 17M UAT Remediation)  
**Symptom:** Clicking "Detect Segments" button after building a reference path crashed the app.  
**Root cause:** `dashboard.py` line 2607 accessed `seed_result.layouts` — but `TrackSeedLoadResult` has `track_locations: list[TrackLocationSeed]`, NOT `layouts`. `AttributeError` in the Qt slot propagated as an app crash.  
**Fix:**
  - `_tm_detect_segments()` now delegates to `_tm_detect_segments_safe()` wrapped in try/except
  - The `seed_result.layouts` access replaced with `get_selected_layout(seed_result, loc_id, lay_id)` (already imported)
  - Outer try/except shows QMessageBox.critical with user-friendly message on any unhandled exception

---

### DEF-17M-UAT-003 — Saved Reference Path Not Discoverable After Restart
**Reported:** 2026-06-25  
**Status:** FIXED (Group 17M UAT Remediation)  
**Symptom:** After saving a reference path and restarting the app, the saved path label was empty. Appeared as if the save had not worked.  
**Root cause:** The file WAS saved correctly (53 KB, `daytona_international_speedway__daytona_international_speedway__road_course.reference_path.json`). After restart, `ctrl._saved_path` is `None` (new controller) so `_tm_update_cal_status()` read empty string and showed nothing. The UI never audited disk for existing files.  
**Fix:**
  - `audit_track_model_files(loc_id, lay_id, search_dir=None)` added to `track_calibration.py` — never raises, returns `TrackModelFileAudit` dataclass with full file metadata
  - `_tm_on_layout_changed()` calls `_tm_audit_and_show_saved_files(loc_id, lay_id)` on every layout selection
  - `_tm_audit_and_show_saved_files()` updates: save-path label (green if loadable, red if unreadable), build-info label (points/confidence/laps), offset label (if offset file found), Detect Segments button enabled state (active if disk file is valid even without active session)

---

### DEF-17N-UAT-004 — Detect Segments Requires Live Session Despite Saved Reference Path
**Reported:** 2026-06-25  
**Status:** FIXED (Group 17N UAT Remediation)  
**Symptom:** After restart with a valid saved reference path (200 pts, conf 1.00), clicking "Detect Segments" showed: "Segment detection requires a live calibration session with lap data. Start a new calibration session to use Build + Detect Segments." DEF-17M-UAT-003 fix made the path discoverable — but Detect Segments still could not run.  
**Root cause:** `detect_track_segments(session)` requires raw `CalibrationLap` objects with per-sample `TelemetrySample` arrays (speed, position, brake, throttle, gear, yaw_rate). The 200-point aggregated `ReferencePath` contains only bucket averages — insufficient for segment detection. Previously `save_reference_path()` wrote ONLY the aggregated reference path JSON; the raw lap samples were discarded on every app restart.  
**Fix:**
  - **`data/track_calibration.py`** — Added `calibration_laps_filename()`, `export_calibration_laps_json()` (saves USABLE laps with all `TelemetrySample` fields), `import_calibration_laps_json()` (reconstructs a `CalibrationSession` from disk). Updated `TrackModelFileAudit` with `calibration_laps_exists`, `calibration_laps_usable_count`, `can_detect_segments` (property: True when both files present), `is_legacy_ref_path_only` (property: True when ref path exists but no laps file). `audit_track_model_files()` now also audits the laps file. `summary_line()` includes lap count.
  - **`data/track_calibration_runtime.py`** — `save_reference_path()` now writes BOTH files in one call: the reference path JSON and the calibration laps JSON. Laps file write is best-effort (ref path save succeeds independently).
  - **`ui/dashboard.py`** — `_tm_detect_segments_safe()` rewritten with three-path logic: (1) active session with usable laps → run immediately; (2) saved laps file found → load via `import_calibration_laps_json()`, reconstruct `CalibrationSession`, run detection; (3) legacy ref path only (no laps file) → informational dialog explaining pre-17N format and what to do. `_tm_audit_and_show_saved_files()` updated: Detect Segments enabled when `ctrl_has_ref OR disk_can_detect OR disk_legacy`; save-path label includes laps count.
  - **`ui/track_modelling_vm.py`** — `format_file_audit_status()` updated: `detail_text` now includes `"{N} laps persisted"` when laps file exists, or `"no lap data saved"` for legacy format. `load_status` now distinguishes "Detect Segments ready — lap data available from disk" vs "Pre-17N format — re-run calibration once to enable Detect Segments after restart".
**Saved file format:** `<loc>__<lay>.calibration_laps.json` alongside `<loc>__<lay>.reference_path.json`  
**Legacy path (pre-17N saves):** is_legacy_ref_path_only=True → informational dialog only; user must run one new calibration session and re-save to enable post-restart Detect Segments.  
**Tests:** `tests/test_group17n_uat_defects.py` — 41 tests covering export/import round-trip, audit detection, can_detect_segments property, detect_track_segments from loaded laps, format_file_audit_status with laps, and full pipeline integration test (save → restart → detect without live session).

---

### DEF-17N-UAT-005 — "No Usable Calibration Laps" Message Lacks Actionable Rejection Diagnostics
**Reported:** 2026-06-25  
**Status:** FIXED (Group 17N UAT-005 Remediation)  
**Symptom:** After a failed calibration build (or after clicking Detect Segments with an active session where build failed), the app showed only: "No USABLE calibration laps in session — record more laps with the Porsche 911 RSR". User could not determine: how many laps were captured, why laps were rejected, what telemetry was missing, or what action to take.  
**Root causes (two bugs combined):**  
  1. **Quality never written back to session laps**: `CalibrationLap.quality` defaults to `REJECTED` and `build_reference_path()` did not mutate the laps after assessment. So even after a successful Build, `detect_track_segments()` filtered by `quality == USABLE` and found none → generic error.  
  2. **Rejection reasons hidden in `result.warnings`**: `_tm_build_path()` only showed `result.errors`, discarding the per-lap rejection details stored in `result.warnings`.  
**Fix:**
  - **`data/track_calibration.py`** — `build_reference_path()` now mutates `CalibrationLap.quality` and `quality_reasons` after `assess_session_laps()` runs (both on success and failure paths). Added `diagnose_calibration_session(session) -> dict` — returns `total_laps`, `usable/rejected/low_confidence_count`, `total_samples`, `per_lap` list, `all_reasons`, `most_common_reason`, `car_id`, `has_any_laps`. Never raises.
  - **`ui/track_modelling_vm.py`** — Added `format_build_failure_diagnostics(result, session=None) -> str` — produces a multi-line diagnostic string with: primary error, lap quality counts, per-lap rejection reasons (from `result.warnings`), car ID, and a context-specific recommended action (different messages for too-few-samples, zero-xyz, off-track, outlier, and general cases). Added `_min_samples()` helper for safe constant access.
  - **`ui/dashboard.py`** — `_tm_build_path()` now calls `_format_build_diag(result, session)` instead of `"\n".join(result.errors)`. The Build Failed dialog shows full per-lap rejection details and a recommended action.
  - **`data/track_segment_detection.py`** — Added `assess_session_laps` to the import from `data.track_calibration`. Added `_build_no_usable_laps_errors(session) -> list[str]` helper that runs fresh quality assessment and returns per-lap rejection details, lap counts, and a context-specific recommended action. `detect_track_segments()` now calls this helper instead of the hardcoded generic string.  
**Post-fix Detect Segments behavior with active session after successful Build:** `build_reference_path()` now marks all USABLE laps as `quality = USABLE` so `detect_track_segments()` finds them immediately — the "no usable laps" path is no longer triggered for this case.  
**Tests:** `tests/test_group17n_uat005_defects.py` — 32 tests covering: `diagnose_calibration_session` (empty, all-usable, all-rejected, mixed, off-track, per-lap detail, car id, total samples, never-raises), `build_reference_path` quality mutation (usable marked, rejected marked, quality_reasons populated, failed build still mutates), `detect_track_segments` diagnostics (empty, rejected with reasons, count in error, car id, off-track advice, UDP advice, successful session works), `format_build_failure_diagnostics` (string returned, counts, primary error, warnings, car id, no-laps message, UDP advice, off-track advice, one-usable recommendation, never-raises), integration (fail→add laps→succeed, warnings surface in dialog text).  
**Manual Daytona retest steps:** Start a new calibration session at Daytona Road Course. Complete at least 2 clean laps at race pace (cross start/finish twice each). Click Stop, then Build Reference Path. Expected: build succeeds or dialog shows per-lap rejection reasons (not generic "record more laps"). If all laps rejected, the dialog identifies the most common reason (e.g., "Too few telemetry samples"). Click Detect Segments immediately after Build — must not show "No USABLE calibration laps" if Build succeeded.

---

### Group 17O — Station Map and Visual Verification (2026-06-25)
**Status:** COMPLETE
**New UAT area:** After Build Reference Path succeeds, a 1 m station map is automatically built from the reference path. The Track Modelling tab shows a track map canvas (centreline, width corridor, corner labels). The Live tab shows the same map with a moving car dot when packets arrive.

**Manual UAT steps — Track Modelling tab:**
1. Select a track/layout in Track Modelling (e.g. Daytona Road Course).
2. Drive 3+ calibration laps.
3. Stop Recording → Build Reference Path → Save Reference Path.
4. Confirm "Station Map" group appears with a rendered track shape (centreline + green shaded width corridor).
5. Confirm corner labels T1..T12 appear (Daytona: 12 corners expected).
6. Start a new calibration session while the map is visible — confirm the car dot moves on the canvas as packets arrive (green = HIGH confidence, orange = MEDIUM, red = LOW).

**Manual UAT steps — Live tab:**
1. Load a saved reference path (or have just built one).
2. Confirm the track map appears in the top-right area of the Live tab (where the logo used to be).
3. Drive a lap — confirm the car dot moves around the track outline.
4. When stationary or in the pit lane, the dot should disappear (is_pit_likely=True).

**Key invariants:**
- Daytona always shows exactly 12 corner labels even if curvature detection finds fewer — placeholders fill gaps.
- Placeholder corners are shown in grey; curvature-detected corners are shown in amber.
- The car dot colour matches the map match confidence: green (≤5 m), orange (5–20 m), red (20–60 m), no dot (>60 m or speed <8 kph).
- The station map only uses X/Y/Z geometry — no brake/gear/throttle/RPM data.

---

### DEF-17O-UAT-001 — Station Map panel shows "No track map loaded" after successful build
**Reported:** 2026-06-25
**Status:** FIXED (Group 17O UAT Remediation)
**Symptom:** After Build Reference Path + Save Reference Path, the Station Map panel still showed "No track map loaded". The track map canvas on both Track Modelling and Live tabs remained empty.
**Root cause:** `_tm_try_build_station_map()` read `ctrl._ref_path` (line 2737). `TrackCalibrationCaptureController` has no `_ref_path` attribute; the reference path lives at `ctrl._last_build_result.reference_path`. `getattr(ctrl, "_ref_path", None)` always returned `None`, so the function exited early without building the map.
**Fix:** Changed `_tm_try_build_station_map(self)` to accept an optional `ref_path` parameter. When `None`, reads `ctrl._last_build_result.reference_path`. Also: in the disk-load branch of `_tm_detect_segments_safe()`, loads saved reference path JSON and calls `_tm_try_build_station_map(ref_path=_ref)` when station map is None.
**Manual Daytona retest steps:** Drive 3+ laps → Build Reference Path → Station Map panel must render immediately. Save Reference Path → map still shown. Restart → click Detect Segments → map appears from saved reference path file.

### DEF-17O-UAT-002 — Segment Review still displays telemetry behaviour as track geometry
**Reported:** 2026-06-25
**Status:** FIXED (Group 17O UAT Remediation Round 1 + Round 2 update)
**Symptom:** Segment Review table contained rows for "Limiter approach", "Kerb/bump candidate", "Gear zones", "Fuel-saving candidate" — telemetry overlay types, not permanent track geometry.
**Root cause:** `_create_seg_review(result)` received the full `SegmentDetectionResult` with all segment types. No filter was applied before populating the Segment Review table.
**Fix Round 1:** Added `_TELEMETRY_OVERLAY_SEG_TYPES = frozenset({GEAR_ZONE, LIMITER_ZONE, FUEL_SAVING_CANDIDATE, KERB_OR_BUMP_CANDIDATE})`. After `_create_seg_review(result)`, filters `review.segments` to exclude overlay types. Segment count label now shows geometry-only count with a note for hidden overlays.
**Fix Round 2 (DEF-17O-UAT-006):** Added `BRAKING_ZONE` and `TRACTION_ZONE` to `_TELEMETRY_OVERLAY_SEG_TYPES`. Both are tagged with "Car-specific — Porsche RSR" warnings in detection output and represent calibration-car behaviour, not universal track geometry.
**Manual Daytona retest steps:** Detect Segments → Segment Review table must contain ONLY geometry rows (straights, corner entry/apex/exit). No limiter, gear zone, kerb, fuel-save, braking zone (Porsche-specific), or traction zone (Porsche-specific) rows.

### DEF-17O-UAT-003 — Daytona runtime reports 5 corners despite seeded expected 12
**Reported:** 2026-06-25
**Status:** FIXED (Group 17O UAT Remediation)
**Symptom:** UI said "Expected corners: 12 ≠ detected: 5". Group 17O claimed placeholder filling guarantees 12 corners, but the label came from the old Group 17E telemetry detection (which found only 5 curvature peaks).
**Root cause:** `_tm_detect_segments_safe()` used `result.detected_corner_count` (old detection, 5) for the corner label. The station map (`_tm_station_map`) with 12 seeded corners was available but not consulted for the label.
**Fix:** After detection succeeds, checks if `_tm_station_map` is available. If so, shows: "{n_seeded} seeded corners | {n_detected_geo} curvature-detected | {n_placeholder} estimated". Falls back to old label only when no station map is present.
**Manual Daytona retest steps:** Detect Segments → Expected corners label must read e.g. "12 seeded corners | 5 curvature-detected | 7 estimated". Must NOT say "detected: 5" as a standalone failure warning.

---

## UAT Defect Register — Round 2 (2026-06-25 Daytona Road Course Run)

### DEF-17O-UAT-004 — Build info label shows only "200 pts" with no station map count
**Reported:** 2026-06-25
**Status:** FIXED (Group 17O UAT Remediation Round 2)
**Symptom:** After Build Reference Path, the Build Info label showed "Path: 200 pts | Confidence: 1.00" only. No station map count was visible in the calibration panel.
**Root cause:** `_tm_update_cal_status()` only read from `ctrl.get_status_summary()` (reference path stats). Station map info was only in `_tm_map_note_lbl` which is inside the Station Map group box (not visible as a primary status).
**Fix:** After building station map in `_tm_try_build_station_map()`, updates `_tm_lbl_build_info` to show `"Path: N pts | Conf: X | Map: N stations / N corners"`.
**Manual Daytona retest steps:** Build Reference Path → Build Info label must show both reference path count ("Path: 200 pts") AND station map count ("Map: ~5800 stations / 12 corners").

### DEF-17O-UAT-005 — Station map shows 5 corners; seed-derived 12 not applied
**Reported:** 2026-06-25
**Status:** FIXED (Group 17O UAT Remediation Round 2)
**Symptom:** After Build Reference Path, station map showed only 5 curvature-detected corners. Daytona seeds expect 12. Placeholder filling was not triggered.
**Root cause:** CRITICAL — `_tm_try_build_station_map()` iterated `self._tm_seed_result.layouts` at line 2770. `TrackSeedLoadResult` has `.track_locations` (a list of `TrackLocationSeed`, each with `.layouts`), NOT a top-level `.layouts` attribute. This raised `AttributeError`, caught by the `except Exception` block, causing the entire `_build_station_map()` call to never execute. `loc_id` was also not read from the location combo (only `lay_id` was).
**Fix:** Replaced `for layout in self._tm_seed_result.layouts:` with `get_selected_layout(self._tm_seed_result, loc_id, lay_id)` — the correct helper already imported. Also reads `loc_id = self._tm_location_combo.currentData()`.
**Manual Daytona retest steps:** Build Reference Path → Station map note must show "12 corners" (not 5). Build info must show "Map: ~5800 stations / 12 corners".

### DEF-17O-UAT-006 — Segment Review shows Braking Zone and Traction Zone rows (Porsche RSR)
**Reported:** 2026-06-25
**Status:** FIXED (Group 17O UAT Remediation Round 2)
**Symptom:** Segment Review contained "Braking zone" and "Traction zone" rows tagged with "Car-specific braking point — Porsche RSR, not universal" and "Car-specific — Porsche RSR traction characteristics" warnings. These are calibration-car behaviour, not universal track geometry.
**Root cause:** `BRAKING_ZONE` and `TRACTION_ZONE` were not in `_TELEMETRY_OVERLAY_SEG_TYPES`. Both are generated by the corner detection loop with car-specific `calibration_car_id` and explicit Porsche RSR warnings.
**Fix:** Added `_TrackSegmentType.BRAKING_ZONE` and `_TrackSegmentType.TRACTION_ZONE` to `_TELEMETRY_OVERLAY_SEG_TYPES`.
**Manual Daytona retest steps:** Detect Segments → Segment Review must contain ONLY: STRAIGHT, CORNER_ENTRY, APEX_ZONE, CORNER_EXIT, START_FINISH rows. No braking zone or traction zone rows.

### DEF-17O-UAT-007 — Track map canvas shows "No track map loaded" after Build Reference Path
**Reported:** 2026-06-25
**Status:** FIXED (Group 17O UAT Remediation Round 2)
**Symptom:** Track Map canvas on both Track Modelling and Live tabs showed "No track map loaded" after Build Reference Path. Station Map note also showed "Station map error: 'TrackSeedLoadResult' object has no attribute 'layouts'".
**Root cause:** Same as DEF-17O-UAT-005. The `AttributeError` from `self._tm_seed_result.layouts` caused the entire `_build_station_map()` call to be skipped. `set_draw_data()` was never called, so the canvas stayed in "No track map loaded" state.
**Fix:** Same fix as DEF-17O-UAT-005 (seed lookup). Once the AttributeError is gone, `_build_station_map()` runs, `set_draw_data()` is called, and the canvas renders the track map.
**Manual Daytona retest steps:** Build Reference Path → Track Map canvas on Track Modelling tab must show the Daytona track outline with 12 corner labels. Track Map on Live tab must also show the map. Status bar at bottom of map must show station count.

### DEF-17O-UAT-008 — No options or status after Detect Segments; map lost on restart
**Reported:** 2026-06-25
**Status:** FIXED (Group 17O UAT Remediation Round 2)
**Symptom:** After Detect Segments, no "Track geometry ready" status was shown. After restarting the app and selecting the same layout, the track map was gone (no auto-load). Turn column in Segment Review was blank for all segments.
**Root cause:** `export_station_map_json()` was never called from the dashboard. Station map existed only in memory. No auto-load logic existed when the layout was reselected. `_tm_refresh_seg_table()` relied on `seg.turn_number` which is `None` for non-apex segments (only apex zones get `turn_number` from `assign_corner_numbers()`).
**Fix:**
- `_tm_try_build_station_map()` now calls `_export_station_map(self._tm_station_map)` after build (best-effort, silent on failure). Saves to `data/track_models/<loc>__<lay>__station_map.json`.
- Added `_tm_try_load_station_map_from_disk(loc_id, lay_id)` — calls `_find_station_map_path()`, loads JSON if found, updates map widgets and note label.
- `_tm_on_layout_changed()` calls `_tm_try_load_station_map_from_disk()` after audit.
- `_tm_refresh_seg_table()` now matches each segment to the nearest `SeededCorner` by `lap_progress_mid` (within 15% threshold) to populate the Turn column for non-apex segments.
**Manual Daytona retest steps:** Build → Detect → close app → reopen → select Daytona Road Course layout → Track Map must appear immediately (loaded from disk). Turn column in Segment Review must show T1..T12 for all corner-related segments (entry, apex, exit).

---

## UAT Defect Register — Group 17P (2026-06-25 Whole-Model Acceptance)

### DEF-17P-UAT-001 — Daytona shows 36 official corners T1-T36 instead of seeded 12
**Reported:** 2026-06-25
**Status:** FIXED (Group 17P)
**Symptom:** After Build Reference Path and build station map, Segment Review showed T1 through T36 as official corners. Seed says 12. No T13-T36 should exist.
**Root cause:** `_detect_corners()` applied the minimum-separation suppression but had no cap on the UPPER bound. If curvature detection found 36 peaks above threshold, all 36 became official `SeededCorner` objects with T1-T36 IDs. The `if len(detected_indices) < corners_expected` cap only relaxed threshold (added MORE corners) but never trimmed when detection > expected.
**Fix:** `data/track_station_map.py` `_detect_corners()`: when `len(detected_indices) > corners_expected`, sort by curvature magnitude, take top N, store excess as `extra_indices`. `_detect_corners()` now returns `(official_corners, extra_peaks)` tuple. `build_track_station_map()` unpacks the tuple and stores extras in `TrackStationMap.extra_curvature_peaks`.

### DEF-17P-UAT-002 — No whole-model acceptance workflow; only per-segment manual review
**Reported:** 2026-06-25
**Status:** FIXED (Group 17P)
**Symptom:** Confirm/Rename/Reject/Needs More Laps/Split Required/Merge Required buttons present. No Accept Track Model button.
**Fix:** In `ui/dashboard.py`: "Segment Review" renamed → "Segment Diagnostics"; 6 per-segment buttons hidden (attrs preserved for backwards-compat with handler methods). "Review Approval" panel replaced by "Track Model Alignment" panel. New buttons: Accept Track Model (green, disabled until ACCEPTABLE_MATCH), Rebuild / Recalibrate. New methods: `_tm_run_alignment()`, `_tm_refresh_alignment_panel()`, `_tm_accept_track_model()`, `_tm_rebuild_model()`.

### DEF-17P-UAT-003 — No seed vs model visual overlay comparison
**Reported:** 2026-06-25
**Status:** ADDRESSED (Group 17P — seed centreline not available in GT7 seed data)
**Symptom:** Track Map only shows telemetry-derived model; no seed overlay.
**Fix:** `ui/track_map_vm.py` `TrackMapDrawData` gains `seed_overlay_note: str` field. Dashboard alignment panel shows: "Seed centreline: not available in GT7 seed data — showing telemetry-derived model only." This is the correct behaviour — GT7 seed data has no geometric centreline; visual overlay of the seed centreline is not possible.

### DEF-17P-UAT-004 — No corners and sectors matched to seed truth in alignment result
**Reported:** 2026-06-25
**Status:** FIXED (Group 17P)
**Fix:** `data/track_model_alignment.py` `TrackModelAlignmentResult` includes `corner_alignments: List[CornerAlignmentResult]` (one per official corner — corner_id, approx_progress, is_placeholder, confidence) and `sector_alignment: SectorAlignmentResult` (seed_sector_count, status, note). Sector boundaries not available in GT7 seed data — status = "not_available" with non-critical note.

### DEF-17P-UAT-005 — Extra curvature peaks promoted to official turns (T13-T36)
**Reported:** 2026-06-25
**Status:** FIXED (Group 17P)
**Fix:** Extra peaks beyond `corners_expected` are stored in `TrackStationMap.extra_curvature_peaks` with XP1..XPn IDs. They are never added to `seeded_corners`. Alignment result reports count as `extra_peaks_suppressed`. Alignment warnings message: "N extra curvature peak(s) suppressed — not promoted to official turns."

### DEF-17P-UAT-006 — No clear accepted/saved end state
**Reported:** 2026-06-25
**Status:** FIXED (Group 17P)
**Fix:** `ui/track_model_alignment_vm.py` `format_alignment_summary()` returns `workflow_state` string with 4 states: "Not built" / "Built — alignment pending" / "Aligned — not accepted" / "Accepted and saved". Dashboard panel shows this as a top-level label with colour coding. `_tm_accept_track_model()` sets `result.accepted=True`, persists to `data/track_models/<loc>__<lay>.accepted_model.json`. `_tm_try_load_accepted_model()` reloads on layout select. `_tm_rebuild_model()` clears accepted status and re-runs alignment.

---

## Manual UAT Acceptance Criteria — Group 17P Whole-Model Acceptance

**Track:** Daytona Road Course (seed: 12 corners)
**Required state:** Station map built from calibration laps, seed loaded

1. **Station map shows exactly 12 official corners** — T1 through T12 only. T13-T36 must NOT appear in Segment Diagnostics or Station Map note.
2. **Extra peaks suppressed label shows > 0** in Track Model Alignment panel (expected ~24 suppressed Daytona peaks).
3. **Workflow state: "Built — alignment pending"** appears immediately after Build Reference Path.
4. **Lap length delta < 5%** — alignment panel shows lap_delta label in green.
5. **Match status: "Good match" or "Acceptable — can accept"** with no blockers.
6. **Accept Track Model button enabled** when match_status = ACCEPTABLE_MATCH.
7. **Click Accept Track Model** → button becomes disabled → "Accepted and saved" state → `data/track_models/daytona_road__full_layout.accepted_model.json` exists on disk.
8. **Restart app, select Daytona Road Course** → Workflow state shows "Accepted and saved" immediately (loaded from disk). Accept button disabled (already accepted).
9. **Click Rebuild / Recalibrate** → accepted status cleared → Workflow state returns to "Aligned — not accepted" → Accept button re-enabled if criteria still pass.
10. **Seed overlay note** appears in alignment panel: "Seed centreline: not available in GT7 seed data — showing telemetry-derived model only."

---

## UAT Defect Register — Group 17Q (2026-06-26 Seed Corner Position Matching)

### DEF-17Q-001 — Cap to 12 may pick wrong corners (not T1–T12 positions)
**Status:** FIXED (Group 17Q)
**Problem:** Group 17P capped at corners_expected=12 by curvature strength. The chosen 12 might not be at the correct Daytona T1–T12 positions.
**Fix:** `data/seed_corner_matching.py` `match_peaks_to_seed_windows()` — greedy assignment: strongest peak per seed window wins. Each seed window (start_progress_pct → end_progress_pct) defines where that specific corner must be. Peaks outside all windows become XP diagnostics. `build_track_station_map()` uses this algorithm when `corner_definitions` are present.

### DEF-17Q-002 — Alignment overstated confidence when seed lacked per-corner positions
**Status:** FIXED (Group 17Q)
**Problem:** `align_track_model()` could reach ACCEPTABLE_MATCH even when seed had no per-corner window data — meaning "12 corners detected" was treated as "positions verified."
**Fix:** ACCEPTABLE_MATCH now requires `corner_defs` present in the layout seed. Without corner_defs: max GOOD_MATCH, `corner_position_match = "NOT_AVAILABLE"`, warning added: "Seed corner location data unavailable — acceptance requires per-corner position windows in seed YAML." Accept Track Model button cannot reach enabled state.

### DEF-17Q-003 — No SeedCornerDefinition type in seed data
**Status:** FIXED (Group 17Q)
**Fix:** `data/track_intelligence.py`: added `SeedCornerDefinition` dataclass (corner_id, display_name, apex_progress_pct, start_progress_pct, end_progress_pct, direction, sector_id, source, confidence). `TrackLayoutSeed.corner_definitions` list field. YAML `corners:` key parsing in `_parse_layout()`. Backward compatible — existing YAML without `corners:` loads with empty list.

### DEF-17Q-004 — Extra peaks not explainable in UI
**Status:** FIXED (Group 17Q)
**Fix:** `TrackStationMap.extra_curvature_peaks` contains all peaks that fell outside seed windows (or beyond cap). `align_track_model()` reports `extra_peaks_suppressed` count. Alignment warning: "N extra curvature peak(s) suppressed — not promoted to official turns." UI alignment panel shows the count.

### DEF-17Q-005 — Accept button required only count match, not position evidence
**Status:** FIXED (Group 17Q)
**Fix:** Acceptance gate (`get_acceptance_button_states()`) is gated on `match_status == ACCEPTABLE_MATCH`. ACCEPTABLE_MATCH is now only reachable when seed has corner_defs AND all windows have matched peaks AND no blockers AND lap delta < 2%. An unmatched window adds a blocker: "Seed corner T{X} has no curvature candidate in its progress window — placeholder used." A placeholder blocks acceptance.

---

## Manual UAT Acceptance Criteria — Group 17Q Seed Corner Position Matching

**Track:** Daytona Road Course (seed: 12 corners with progress windows T1–T12)
**Pre-requisite:** Daytona `corners:` list added to `track_modelling_seed.yaml` with 12 entries, each with `apex_progress_pct`, `start_progress_pct`, `end_progress_pct`.
**Required state:** Station map built from calibration laps, seed with corner defs loaded.

1. **Alignment panel shows "Seed corner positions" row** with value "Available (12/12 matched)" when all 12 windows have a peak. OR "Available (11/12 matched)" if one window was empty.
2. **"Corners matched" row** shows "12 / 12" when seed positions available, "N/A (no seed positions)" when seed has no corner defs.
3. **"Corner pos match" row** shows "Pass" (green) when all 12 matched, "Partial" (orange) when some missed, "Fail" (red) when most missed. "Not available" (grey) when no seed corner defs.
4. **Seed YAML without `corners:` key** — alignment panel shows "Seed corner positions: Unavailable — count only". Accept Track Model button must be DISABLED even if corner count matches perfectly.
5. **One noisy Daytona lap with 36 curvature peaks** — station map shows exactly T1–T12 (12 official). Extra 24 peaks appear as XP1..XP24 in `extra_curvature_peaks`. Alignment panel `extra_peaks` row shows "24".
6. **Accept Track Model button ENABLED** only when: seed has corner defs, all 12 windows matched, lap delta < 2%, no blockers.
7. **Accept Track Model button DISABLED** when: seed has no corner defs (even if corner count == 12), OR any seed window has a placeholder (peak missing), OR lap delta ≥ 2%, OR any blocker present.
8. **T13+ must not appear** as an official corner ID in the station map or alignment result under any tested telemetry condition.
9. **JSON round-trip backward compat** — old `accepted_model.json` files (without `seed_corner_positions_available`, `corner_position_match`, `corners_matched`) must load with defaults: `False`, `"NOT_AVAILABLE"`, `0`. No crash on load.
10. **After accepting the model**, restart app, reload Daytona layout — workflow state shows "Accepted and saved". Alignment panel shows all seed corner position rows with the same values as at accept time.
11. **Clicking Rebuild / Recalibrate** clears the entire station map (not just the accepted flag). Alignment panel resets to "Not built". A dialog appears: "Station map cleared. Start Calibration and drive clean laps to rebuild the track model." Map widget goes blank.
12. **Seed with corner defs but noisy telemetry where one window gets two peaks** — MULTIPLE_CANDIDATES status for that window (shown in notes). Stronger peak is selected. Weaker peak becomes XP. Accept may still proceed if all other windows are MATCHED.

---

## DEF-17R Defect Register (Group 17R — 2026-06-26)

### DEF-17R-001 — Corner labels are curvature peaks, not verified positions
**Reported:** 2026-06-26
**Status:** FIXED (Group 17R)
**Symptom:** Alignment panel said "Unavailable — count only". User correctly identified that T1-T12 labels in the station map are strongest curvature peaks, not positions verified against the real Daytona T1-T12. The label was ambiguous.
**Root cause:** `format_alignment_summary()` returned "Unavailable — count only" — doesn't explain what the labels actually are.
**Fix:** `seed_position_status` now returns: *"Unavailable — corner labels are curvature peaks, not verified positions"*. This makes explicit that T1-T12 are curvature-ranked peaks, not positionally matched to the seed.

### DEF-17R-002 — seed_overlay_note never set in TrackMapDrawData
**Reported:** 2026-06-26
**Status:** FIXED (Group 17R)
**Symptom:** `TrackMapDrawData.seed_overlay_note` field existed but was always `""` at runtime. The `_tm_al_seed_overlay_note` label in the dashboard used static text that never updated.
**Root cause:** `build_track_map_draw_data()` never set the field. `project_to_screen()` didn't pass it through.
**Fix:** `build_track_map_draw_data()` sets `seed_overlay_note` from `station_map.seed_corner_positions_available`. `project_to_screen()` passes it through.

### DEF-17R-003 — No explicit seed map source in alignment panel
**Reported:** 2026-06-26
**Status:** FIXED (Group 17R)
**Symptom:** User couldn't tell from the alignment panel what truth source the seed uses (metadata only / corner windows / centreline).
**Root cause:** No "Seed truth source" row existed.
**Fix:** New "Seed truth source" row in the alignment panel. `format_alignment_summary()` returns new `"seed_truth_source"` key: *"Metadata only — no coordinate or window data"* or *"Seed corner windows (N defs)"*.

### DEF-17R-004 — Old "Corner count mismatch" warnings leaked into Segment Diagnostics
**Reported:** 2026-06-26
**Status:** FIXED (Group 17R)
**Symptom:** Segment Diagnostics showed "Detected 5 corners vs expected 12 (difference 7)" even though the station map showed 12 seeded corners.
**Root cause:** `detect_track_segments()` uses telemetry speed-minima to count corners. For the Daytona RSR calibration, only 5 behavioural corners were detected. The warning was surfaced even when the station map's 12 curvature-detected/seeded corners were already authoritative.
**Fix:** `_tm_detect_segments_safe()` now filters out "Corner count mismatch" and "corners vs expected" warnings when a station map with seeded corners is present. These warnings are irrelevant to the station map geometry.

### DEF-17R-005 — Rebuild/Recalibrate button was a silent no-op
**Reported:** 2026-06-26
**Status:** FIXED (Group 17R)
**Symptom:** Clicking "Rebuild / Recalibrate" appeared to do nothing. The map stayed, the alignment panel stayed, no message appeared.
**Root cause:** `_tm_rebuild_model()` only cleared `result.accepted` and re-ran `_tm_run_alignment()` — it didn't touch the station map at all.
**Fix:** `_tm_rebuild_model()` now:
1. Sets `self._tm_station_map = None` and `self._tm_alignment_result = None`
2. Pushes empty draw data to both map widgets (map goes blank)
3. Calls `_tm_refresh_alignment_panel(None)` (panel resets to "Not built")
4. Shows dialog: *"Station map cleared. Start Calibration and drive clean laps to rebuild the track model."*
**Manual Daytona retest:** With station map built, click Rebuild / Recalibrate → station map widget goes blank → alignment panel shows "Not built" → dialog appears → clicking Start Calibration resumes.

### DEF-17R-006 — Lap offset calibration UI unexplained
**Reported:** 2026-06-26
**Status:** FIXED (Group 17R)
**Symptom:** The Lap Offset Calibration group had vague note text. Users didn't know what the status states meant.
**Root cause:** The `_off_note` QLabel said "Zero-offset is provisional. Validate at the Start/Finish line..." — no explanation of what the three status states are.
**Fix:** Updated `_off_note` to explain: what lap offset calibration does, and the three status states: Not loaded / Zero offset provisional / Calibrated.

---

## Manual UAT — Group 17R (Daytona Road Course, Porsche RSR)

| # | Step | Expected Result | Pass/Fail |
|---|------|-----------------|-----------|
| 1 | Select Daytona Road Course / Daytona layout | Location and layout populate. | |
| 2 | Build Reference Path (drive calibration laps). | Station map builds. | |
| 3 | Check alignment panel "Seed truth source" row. | Shows "Metadata only — no coordinate or window data". | |
| 4 | Check alignment panel "Seed corner positions" row. | Shows "Unavailable — corner labels are curvature peaks, not verified positions". | |
| 5 | Check alignment panel "Match status" row. | Shows "Good match" or lower. NOT "Acceptable — can accept". | |
| 6 | Check "Accept Track Model" button. | Disabled (greyed out). Cannot accept without seed corner windows. | |
| 7 | Detect Segments. | Segment Diagnostics status text DOES NOT contain "Detected N corners vs expected 12". | |
| 8 | Check Segment Diagnostics summary shows 18 segments (or similar). | No "corner count mismatch" warning in the count. | |
| 9 | Click Rebuild / Recalibrate. | Dialog appears: "Station map cleared. Start Calibration and drive clean laps...". Map widget goes blank. Alignment panel shows "Not built". | |
| 10 | Check lap offset group "not loaded" status (before creating offset). | QLabel explanation text includes "Not loaded", "Zero offset", "Calibrated" in its description. | |
| 11 | Create Zero Offset. | Status shows "Zero offset — provisional (validate at S/F line)". | |
| 12 | Rebuild reference path and station map after reset. | Map redraws with corners. Alignment panel recalculates. | |
| 13 | Check `seed_overlay_note` is set (inspect via debug or check UAT manually). | Track map status text is informative. Seed overlay note would show "Seed centreline not available...". | |
| 14 | Confirm existing full suite still passes. | 2155 pass / 5 skip / 0 fail. | |
| 15 | Confirm 38 new Group 17R tests pass. | `tests/test_group17r_seed_overlay_alignment.py — 38 passed`. | |

---

## Manual UAT — Group 17S (Daytona Road Course, enriched seed data)

### Defect register

| ID | Title | Status |
|----|-------|--------|
| DEF-17S-001 | Daytona seed lacked corner window truth | Fixed — YAML enriched with 12 corners |
| DEF-17S-002 | Corner complexes not represented | Fixed — T10/T11 + BusStop complexes added |
| DEF-17S-003 | Lap delta 5.1% was only a warning | Fixed — now a BLOCKER |
| DEF-17S-004 | Turn assignment used curvature rank | Fixed — seed-window-based assignment |
| DEF-17S-005 | Legacy warnings still leaked post-map-load | Fixed — _tm_refresh_seg_diagnostics_labels() |
| DEF-17S-006 | No seed audit diagnostics | Fixed — "Seed data available" row in panel |

### UAT steps

| # | Step | Expected Result | Pass/Fail |
|---|------|-----------------|-----------|
| 1 | Select Daytona International Speedway → Road Course | Combos populate. | |
| 2 | Check alignment panel "Seed data available" row (before building station map). | Shows "lap length, 3 sectors, 12 corner windows, 2 complexes, no centreline". | |
| 3 | Check alignment panel "Seed truth source" row. | Shows "Metadata only — no coordinate or window data" (no station map built yet). | |
| 4 | Build Reference Path and station map (drive calibration laps). | Station map builds with corners. | |
| 5 | Check alignment panel "Match status" after build. | Shows "Partial match" (5.1% lap delta creates a blocker). NOT "Good match". | |
| 6 | Check alignment panel "Blockers" row. | Contains text about "Lap length mismatch" (5.1% > 5% threshold). | |
| 7 | Check alignment panel "Seed corner positions" row. | Shows "Available (N/12 matched)" — windows are now present so position matching fires. | |
| 8 | Detect Segments. | Status does NOT contain "Detected N corners vs expected 12". | |
| 9 | Check Segment Diagnostics table Turn column for the pre-T1 straight. | Straight row 0–7.3% has no Turn assigned (empty or "—"). NOT "T2". | |
| 10 | Check Segment Diagnostics table for a row at ~8% progress. | Turn column shows "T1" (from seed window assignment). | |
| 11 | Load station map from disk (restart app, re-select Daytona). | Status text does NOT show old "corners vs expected" warning. | |
| 12 | Check corner complexes: confirm T10 and T11 are noted as a complex. | Seed data available shows "2 complexes". | |
| 13 | Check corner complexes: confirm Bus Stop (T1+T2) is a complex. | Confirmed by YAML inspection or debug view. | |
| 14 | Confirm existing full suite still passes. | 2191 pass / 5 skip / 0 fail. | |
| 15 | Confirm 36 new Group 17S tests pass. | `tests/test_group17s_seed_definition_authoring.py — 36 passed`. | |

---

## GROUP 17T — Seed Coordinate Map Import and Full-Lap Alignment

### Defect register

| ID | Title | Status |
|----|-------|--------|
| DEF-17T-001 | Seed centreline/coordinate map unavailable blocks true matching | Fixed — SeedCoordinateMap model + file loader added |
| DEF-17T-002 | Compare imported seed map vs modelled telemetry map | Fixed — align_maps_geometry() in track_map_geometry_alignment.py |
| DEF-17T-003 | Detect and explain missing track sections | Fixed — _detect_missing_sections() with progress-range description |
| DEF-17T-004 | Stop using 200-point reference path for serious alignment | Fixed — align_maps_geometry() uses station_map.stations directly |
| DEF-17T-005 | Handle coordinate transform between seed map and GT7 telemetry map | Fixed — estimate_coordinate_transform() with coarse+fine rotation scan |
| DEF-17T-006 | Corner and sector matching should use coordinate/progress truth | Fixed — _match_corners() and _match_sectors() use seed marker fields |
| DEF-17T-007 | UI overlay must show seed vs modelled map | Fixed — seed_centreline field in TrackMapDrawData; projected in project_to_screen() |
| DEF-17T-008 | Recalibration must guide user toward fixing full-lap mismatch | Fixed — _tm_rebuild_model() dialog with 4-step guidance |

### UAT steps (Daytona Road Course — no seed coordinate map file present)

| # | Step | Expected Result | Pass/Fail |
|---|------|-----------------|-----------|
| 1 | Select Daytona International Speedway → Road Course | Combos populate correctly. | |
| 2 | Check alignment panel "Seed data available" row | Shows "lap length, 3 sectors, 12 corner windows, 2 complexes, no centreline". | |
| 3 | Check alignment panel "Geometry match" row (no station map built) | Shows "—". | |
| 4 | Build station map (drive calibration laps, Daytona Road Course). | Station map builds; alignment result computed. | |
| 5 | Check alignment panel "Geometry match" row after build (no seed coordinate map file). | Shows "Length only — seed map unavailable (5.9% delta)" or similar. | |
| 6 | Check alignment panel "Blockers" row. | Contains lap length mismatch blocker (5.9% > 5% threshold). | |
| 7 | Accept Track Model button. | Disabled — blockers prevent acceptance. | |
| 8 | Click "Rebuild / Recalibrate" button. | Dialog appears with 4-step guidance: "Start Calibration mode before leaving pits", "Drive 2–3 full clean laps crossing S/F line", "Avoid pit-lane entries", "Check correct layout is selected". | |
| 9 | Confirm station map cleared after rebuild dialog. | Alignment panel resets to "Not built". | |
| 10 | Manually create a seed coordinate map JSON at data/track_seed_maps/ for Daytona. | File loads on next build; "Geometry match" row shows coordinate comparison result. | |
| 11 | Confirm 55 new Group 17T tests pass. | `tests/test_group17t_seed_coordinate_map.py — 55 passed`. | |
| 12 | Confirm full suite still passes. | 2246 pass / 5 skip / 0 fail. | |

---

## GROUP 17U — Track Library Schema and Seed Data Registry

### Defect register

| ID | Title | Status |
|----|-------|--------|
| DEF-17U-001 | Ad hoc seed/coordinate file discovery is unversioned and unmanaged | Fixed — `data/track_library.py` + `data/track_library/` directory structure |
| DEF-17U-002 | No per-layout availability summary | Fixed — `TrackLibraryAvailability` dataclass in manifest |
| DEF-17U-003 | Semantic model (corners/sectors/complexes) mixed with geometry | Fixed — separated into `semantic_model.json` |
| DEF-17U-004 | No per-layout validation threshold configuration | Fixed — `validation_rules.json` with `ValidationAcceptance` dataclass |
| DEF-17U-005 | No data provenance tracking per layout | Fixed — `source_manifest.json` with sources and fields_estimated |
| DEF-17U-006 | Alignment panel does not show seed source | Fixed — "Seed source" row added; `format_alignment_summary()` returns `"seed_source"` key |
| DEF-17U-007 | Legacy seed map files will be unreachable without backward compatibility | Fixed — `resolve_seed_coordinate_map()` tries library first, falls back to legacy |

### UAT steps (Daytona Road Course — library skeleton present, no geometry file)

| # | Step | Expected Result | Pass/Fail |
|---|------|-----------------|-----------|
| 1 | Select Daytona International Speedway → Road Course on Track Modelling tab. | Combos populate; layout panel shows correct display name and lap length. | |
| 2 | Check alignment panel "Seed source" row (no station map built). | Shows "—" (alignment not yet computed). | |
| 3 | Build station map. | Station map builds; alignment result computed. | |
| 4 | Check alignment panel "Seed source" row after build. | Shows "Unavailable" (no geometry.seed_map.json in library or legacy). | |
| 5 | Check alignment panel "Seed data available" row. | Shows "lap length, 3 sectors, 12 corner windows, 2 complexes, no centreline". | |
| 6 | Check alignment panel "Blockers" row. | Contains lap length mismatch blocker (5.9% > 5%). | |
| 7 | Accept Track Model button. | Disabled — blockers present. | |
| 8 | Place a test geometry.seed_map.json in the library layout directory. Set seed_geometry=true in manifest.json. | App reads the file on next alignment; "Seed source" row shows "Track library". | |
| 9 | Confirm 83 new Group 17U tests pass. | `tests/test_group17u_track_library_schema.py — 83 passed`. | |
| 10 | Confirm full suite still passes. | 2329 pass / 5 skip / 0 fail. | |
