"""Group 17Q — Seed Corner Position Matching and Acceptance Integrity.

Tests for DEF-17Q-001 through DEF-17Q-005:
  001: Correct 12 peaks selected by seed window (not just any 12)
  002: Acceptance blocked / honest when seed lacks per-corner position data
  003: Seed corner progress-window matching function
  004: Extra curvature peaks are diagnostic only — never official
  005: Accept requires seed position evidence

Naming convention: TestDef17QxyzDescription (class) → test_what_happens (method).
"""
from __future__ import annotations

import pytest
from typing import List, Optional

from data.seed_corner_matching import (
    CornerMatchStatus,
    CornerCandidateMatch,
    match_peaks_to_seed_windows,
)
from data.track_intelligence import SeedCornerDefinition
from data.track_model_alignment import (
    TrackModelAlignmentResult,
    TrackModelMatchStatus,
    SectorAlignmentResult,
    CornerAlignmentResult,
    align_track_model,
    export_accepted_model_json,
    import_accepted_model_json,
    find_accepted_model_path,
)
from data.track_station_map import TrackStationMap, SeededCorner, StationPoint
from ui.track_model_alignment_vm import (
    format_alignment_summary,
    get_acceptance_button_states,
)


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _make_even_windows(n: int, total_pct: float = 100.0):
    """Return (starts, apexes, ends, ids) for n evenly-spaced windows."""
    step = total_pct / n
    starts = []
    apexes = []
    ends   = []
    ids    = []
    for i in range(n):
        centre = (i + 0.5) * step
        starts.append(max(0.0, centre - step * 0.4))
        apexes.append(centre)
        ends.append(min(100.0, centre + step * 0.4))
        ids.append(f"T{i + 1}")
    return starts, apexes, ends, ids


def _make_peaks_at(progresses: List[float], curvature: float = 0.02):
    """Return (peak_progresses, peak_curvatures) lists."""
    return list(progresses), [curvature] * len(progresses)


def _make_seed_corner_defs(n: int) -> List[SeedCornerDefinition]:
    """Build n evenly-distributed SeedCornerDefinition objects."""
    step = 100.0 / n
    defs = []
    for i in range(n):
        centre = (i + 0.5) * step
        defs.append(SeedCornerDefinition(
            corner_id          = f"T{i + 1}",
            display_name       = f"Turn {i + 1}",
            apex_progress_pct  = centre,
            start_progress_pct = max(0.0, centre - step * 0.4),
            end_progress_pct   = min(100.0, centre + step * 0.4),
        ))
    return defs


def _make_station_map_from_corners(
    corners: List[SeededCorner],
    extra_peaks: Optional[List[SeededCorner]] = None,
    lap_length_m: float = 5800.0,
    confidence: float = 0.85,
    seed_pos_available: bool = False,
) -> TrackStationMap:
    """Build a minimal TrackStationMap with given corners for alignment tests."""
    n = 500  # enough for alignment (> 200 min)
    stations = [
        StationPoint(
            station_m    = float(i) * lap_length_m / n,
            progress_pct = float(i) / n * 100.0,
            x=float(i), y=0.0, z=float(i),
        )
        for i in range(n)
    ]
    return TrackStationMap(
        track_location_id  = "test",
        layout_id          = "test",
        lap_length_m       = lap_length_m,
        spacing_m          = 1.0,
        stations           = stations,
        seeded_corners     = corners,
        extra_curvature_peaks = extra_peaks or [],
        confidence_overall = confidence,
        corners_expected   = len(corners),
        corners_detected   = sum(1 for c in corners if not c.is_seeded_placeholder),
        seed_corner_positions_available = seed_pos_available,
    )


def _make_layout_seed_with_defs(
    corners_expected: int,
    length_m: float,
    defs: Optional[List[SeedCornerDefinition]] = None,
):
    """Duck-typed layout seed object with optional corner_definitions."""
    class _Seed:
        pass
    seed = _Seed()
    seed.corners_expected   = corners_expected
    seed.length_m           = length_m
    seed.sectors            = None
    seed.corner_definitions = defs or []
    return seed


def _make_12_corners(lap_m: float = 5800.0) -> List[SeededCorner]:
    """Return 12 SeededCorner objects at evenly-spaced positions, all detected."""
    corners = []
    for i in range(12):
        progress = (i + 0.5) / 12.0  # 0–1
        corners.append(SeededCorner(
            corner_id        = f"T{i + 1}",
            display_name     = f"T{i + 1}",
            approx_station_m = progress * lap_m,
            approx_progress  = progress,
            is_seeded_placeholder = False,
            confidence       = 0.8,
        ))
    return corners


# ===========================================================================
# DEF-17Q-003: match_peaks_to_seed_windows function
# ===========================================================================

class TestDef17QMatchPeaksToSeedWindows:
    """Pure unit tests of the matching algorithm."""

    def test_single_peak_in_window_gives_matched(self):
        progs  = [12.5]
        curvs  = [0.03]
        starts, apexes, ends, ids = _make_even_windows(1)  # 0–100
        offs, extras, matches = match_peaks_to_seed_windows(
            progs, curvs, starts, apexes, ends, ids,
        )
        assert offs[0] == 0
        assert matches[0].match_status == CornerMatchStatus.MATCHED
        assert len(extras) == 0

    def test_strongest_peak_selected_when_multiple_in_window(self):
        # Two peaks in the only window; stronger curvature wins
        progs  = [10.0, 12.0]
        curvs  = [0.01, 0.04]   # peak 1 (index 1) is stronger
        starts = [0.0]; apexes = [12.0]; ends = [20.0]; ids = ["T1"]
        offs, extras, matches = match_peaks_to_seed_windows(
            progs, curvs, starts, apexes, ends, ids,
        )
        assert offs[0] == 1, "Stronger peak (index 1) should win"
        assert matches[0].match_status == CornerMatchStatus.MULTIPLE_CANDIDATES
        assert 0 in extras, "Weaker peak becomes extra"

    def test_candidate_outside_window_becomes_extra(self):
        # Peak at 80%: only window covers 0–20%
        progs  = [80.0]
        curvs  = [0.03]
        starts = [0.0]; apexes = [10.0]; ends = [20.0]; ids = ["T1"]
        offs, extras, matches = match_peaks_to_seed_windows(
            progs, curvs, starts, apexes, ends, ids,
        )
        assert offs[0] == -1, "No peak in window — should be -1"
        assert matches[0].match_status == CornerMatchStatus.NO_CANDIDATE_IN_WINDOW
        assert 0 in extras, "Out-of-window peak is extra"

    def test_no_candidate_in_window_returns_minus_one(self):
        progs  = []
        curvs  = []
        starts, apexes, ends, ids = _make_even_windows(3)
        offs, extras, matches = match_peaks_to_seed_windows(
            progs, curvs, starts, apexes, ends, ids,
        )
        assert all(o == -1 for o in offs)
        assert all(m.match_status == CornerMatchStatus.NO_CANDIDATE_IN_WINDOW for m in matches)
        assert len(extras) == 0

    def test_overlapping_windows_each_get_different_peak(self):
        # Windows slightly overlap; two peaks, each in both windows.
        # Greedy: strongest curvature pair wins first.
        progs  = [20.0, 40.0]
        curvs  = [0.02, 0.05]
        starts = [10.0, 30.0]; apexes = [22.0, 42.0]; ends = [35.0, 55.0]; ids = ["T1", "T2"]
        offs, extras, matches = match_peaks_to_seed_windows(
            progs, curvs, starts, apexes, ends, ids,
        )
        # Peak 1 (idx 1, curv=0.05) wins first — either T1 or T2
        # Peak 0 (idx 0, curv=0.02) wins the remaining window
        # Result: each window has exactly one peak assigned
        assigned = [o for o in offs if o >= 0]
        assert len(assigned) == 2
        assert len(set(assigned)) == 2, "Both peaks should be assigned (no duplication)"

    def test_candidate_just_inside_window_edge_is_matched(self):
        # Peak exactly at window start boundary
        progs = [10.0]  # window starts at 10.0
        curvs = [0.03]
        starts = [10.0]; apexes = [15.0]; ends = [20.0]; ids = ["T1"]
        offs, extras, matches = match_peaks_to_seed_windows(
            progs, curvs, starts, apexes, ends, ids,
        )
        assert offs[0] == 0
        assert matches[0].match_status == CornerMatchStatus.MATCHED

    def test_candidate_just_outside_window_is_not_matched(self):
        # Peak at 9.99%: window starts at 10.0
        progs = [9.9]
        curvs = [0.03]
        starts = [10.0]; apexes = [15.0]; ends = [20.0]; ids = ["T1"]
        offs, extras, matches = match_peaks_to_seed_windows(
            progs, curvs, starts, apexes, ends, ids,
        )
        assert offs[0] == -1
        assert matches[0].match_status == CornerMatchStatus.NO_CANDIDATE_IN_WINDOW

    def test_36_peaks_12_windows_gives_12_official_and_24_extras(self):
        """DEF-17Q-001: Daytona scenario — 36 detected peaks, 12 seed windows."""
        n_peaks   = 36
        n_windows = 12
        step      = 100.0 / n_peaks
        # Peaks evenly at ~2.7% intervals
        progs = [(i + 0.5) * step for i in range(n_peaks)]
        curvs = [0.02] * n_peaks

        starts, apexes, ends, ids = _make_even_windows(n_windows)

        offs, extras, matches = match_peaks_to_seed_windows(
            progs, curvs, starts, apexes, ends, ids,
        )
        # Exactly 12 official corners (one per window), rest extras
        assert len(offs) == n_windows
        official_count = sum(1 for o in offs if o >= 0)
        assert official_count == n_windows, f"Expected 12 official, got {official_count}"
        assert len(extras) == n_peaks - official_count
        # No -1 in offs (all windows have a peak, since peaks spread evenly)
        assert all(o >= 0 for o in offs)


# ===========================================================================
# DEF-17Q-001: Correct peaks selected via seed windows (not just top-N)
# ===========================================================================

class TestDef17QCorrectPeaksSelected:
    """align_track_model uses seed windows for corner selection when available."""

    def test_all_12_corners_matched_when_defs_cover_positions(self):
        """12 corners at known positions, seed windows covering them → all MATCHED."""
        defs    = _make_seed_corner_defs(12)
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners, seed_pos_available=True)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs)
        result  = align_track_model(sm, seed)
        assert result.corners_matched == 12, (
            f"Expected 12 matched; got {result.corners_matched}. "
            f"Matches: {[(m.seed_corner_id, m.match_status) for m in result.corner_candidate_matches]}"
        )
        assert result.corner_position_match == "PASS"

    def test_no_t13_plus_in_official_corners_under_noisy_telemetry(self):
        """DEF-17Q-001: Extra XP peaks do not become official T13+ corners."""
        corners    = _make_12_corners()
        xp_extras  = [
            SeededCorner(f"XP{i}", f"XP{i}", 300.0 * i, 0.05 * i, False, 0.5)
            for i in range(1, 25)
        ]
        sm = _make_station_map_from_corners(
            corners, extra_peaks=xp_extras, seed_pos_available=True,
        )
        assert all(c.corner_id.startswith("T") and not c.corner_id.startswith("T1") or
                   c.corner_id in ["T10", "T11", "T12"] or
                   c.corner_id in [f"T{i}" for i in range(1, 13)]
                   for c in sm.seeded_corners)
        # More specifically: no T13 or beyond
        official_ids = {c.corner_id for c in sm.seeded_corners}
        for illegal in [f"T{i}" for i in range(13, 40)]:
            assert illegal not in official_ids, f"{illegal} must not be an official corner"

    def test_placeholder_when_no_peak_in_seed_window(self):
        """One window has no peak → corner is placeholder → NO_CANDIDATE_IN_WINDOW."""
        # 12 corners but T7 is a placeholder (curvature missed it)
        corners = _make_12_corners()
        corners[6] = SeededCorner(
            "T7", "T7",
            approx_station_m = corners[6].approx_station_m,
            approx_progress  = corners[6].approx_progress,
            is_seeded_placeholder = True,
            confidence = 0.2,
        )
        defs = _make_seed_corner_defs(12)
        sm   = _make_station_map_from_corners(corners, seed_pos_available=True)
        seed = _make_layout_seed_with_defs(12, sm.lap_length_m, defs)
        result = align_track_model(sm, seed)
        t7_match = next(m for m in result.corner_candidate_matches if m.seed_corner_id == "T7")
        assert t7_match.match_status == CornerMatchStatus.NO_CANDIDATE_IN_WINDOW
        assert result.corners_matched < 12, "One placeholder means not all 12 matched"


# ===========================================================================
# DEF-17Q-002: Position match status when seed lacks per-corner data
# ===========================================================================

class TestDef17QSeedPositionUnavailable:
    """When seed has only corners_expected (no windows), be honest in alignment."""

    def test_no_corner_defs_gives_not_available_status(self):
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs=None)
        result  = align_track_model(sm, seed)
        assert result.corner_position_match == "NOT_AVAILABLE"
        assert result.seed_corner_positions_available is False

    def test_no_corner_defs_caps_at_good_match(self):
        """Without seed positions, match status is at most GOOD_MATCH."""
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs=None)
        result  = align_track_model(sm, seed)
        assert result.match_status != TrackModelMatchStatus.ACCEPTABLE_MATCH, (
            "Cannot reach ACCEPTABLE_MATCH without seed position data"
        )

    def test_seed_position_unavailable_warning_in_result(self):
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs=None)
        result  = align_track_model(sm, seed)
        assert any("corner" in w.lower() and "unavailable" in w.lower() for w in result.warnings), (
            "Should warn that seed corner location data is unavailable"
        )

    def test_each_official_corner_marked_seed_position_unavailable(self):
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs=None)
        result  = align_track_model(sm, seed)
        assert all(
            m.match_status == CornerMatchStatus.SEED_POSITION_UNAVAILABLE
            for m in result.corner_candidate_matches
        )


# ===========================================================================
# DEF-17Q-005: Acceptance gate requires seed position evidence
# ===========================================================================

class TestDef17QAcceptanceGate:
    """Accept Track Model requires seed corner position data."""

    def test_accept_enabled_without_seed_positions_good_match(self):
        """Corner count matches but no seed positions → max GOOD_MATCH → accept NOW enabled (Group 24 AC3)."""
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs=None)
        result  = align_track_model(sm, seed)
        states  = get_acceptance_button_states(result, has_station_map=True)
        assert states["accept"], (
            f"Accept should be enabled for GOOD_MATCH without blockers (status={result.match_status})"
        )

    def test_accept_enabled_when_all_seed_windows_matched(self):
        """All 12 windows matched + lap delta within 2% → ACCEPTABLE_MATCH → accept enabled."""
        defs    = _make_seed_corner_defs(12)
        corners = _make_12_corners(lap_m=5800.0)
        sm      = _make_station_map_from_corners(corners, seed_pos_available=True, lap_length_m=5800.0, confidence=0.85)
        seed    = _make_layout_seed_with_defs(12, 5800.0, defs)
        result  = align_track_model(sm, seed)
        assert result.match_status == TrackModelMatchStatus.ACCEPTABLE_MATCH, (
            f"Expected ACCEPTABLE_MATCH; got {result.match_status}. "
            f"blockers={result.blockers} corner_pos={result.corner_position_match}"
        )
        states = get_acceptance_button_states(result, has_station_map=True)
        assert states["accept"], "Accept should be enabled when all seed windows matched"

    def test_accept_disabled_with_unmatched_seed_window(self):
        """Placeholder in T7 → NO_CANDIDATE_IN_WINDOW → blocker → accept disabled."""
        defs = _make_seed_corner_defs(12)
        corners = _make_12_corners()
        corners[6] = SeededCorner("T7", "T7", corners[6].approx_station_m,
                                  corners[6].approx_progress, True, 0.2)
        sm     = _make_station_map_from_corners(corners, seed_pos_available=True)
        seed   = _make_layout_seed_with_defs(12, sm.lap_length_m, defs)
        result = align_track_model(sm, seed)
        states = get_acceptance_button_states(result, has_station_map=True)
        assert not states["accept"], "Unmatched seed window must block acceptance"
        assert result.blockers, "Should have at least one blocker"

    def test_accept_enabled_for_good_match_without_blockers(self):
        """Group 24 AC3: GOOD_MATCH with no blockers → accept enabled."""
        r = TrackModelAlignmentResult(
            match_status           = TrackModelMatchStatus.GOOD_MATCH,
            seed_corners_expected  = 12,
            model_corners_found    = 12,
            extra_peaks_suppressed = 0,
            placeholder_count      = 0,
            lap_length_m_model     = 5800.0,
            lap_length_m_seed      = 5800.0,
            lap_length_delta_pct   = 0.5,
            station_count          = 500,
            confidence             = 0.85,
            corner_alignments      = [],
            sector_alignment       = SectorAlignmentResult(0, "not_available", "test"),
            blockers               = [],
            warnings               = ["Seed corner location data unavailable"],
            accepted               = False,
        )
        states = get_acceptance_button_states(r, has_station_map=True)
        assert states["accept"], "GOOD_MATCH with no blockers should enable accept (Group 24 AC3)"


# ===========================================================================
# DEF-17Q-004: Extra curvature peaks are diagnostic only
# ===========================================================================

class TestDef17QExtraPeaksDiagnostic:
    """XP peaks are never in the official corner list."""

    def test_extra_peaks_not_in_official_corners(self):
        corners   = _make_12_corners()
        xp_extras = [SeededCorner(f"XP{i}", f"XP{i}", 100.0 * i, 0.02 * i, False, 0.5)
                     for i in range(1, 5)]
        sm = _make_station_map_from_corners(corners, extra_peaks=xp_extras)
        official_ids = {c.corner_id for c in sm.seeded_corners}
        for xp in xp_extras:
            assert xp.corner_id not in official_ids, f"{xp.corner_id} must not be official"

    def test_extra_peaks_reported_in_alignment_summary(self):
        corners   = _make_12_corners()
        xp_extras = [SeededCorner(f"XP{i}", f"XP{i}", 100.0 * i, 0.02 * i, False, 0.5)
                     for i in range(1, 4)]
        sm     = _make_station_map_from_corners(corners, extra_peaks=xp_extras)
        seed   = _make_layout_seed_with_defs(12, sm.lap_length_m, defs=None)
        result = align_track_model(sm, seed)
        assert result.extra_peaks_suppressed == 3
        summary = format_alignment_summary(result)
        assert summary["extra_peaks"] == "3"


# ===========================================================================
# DEF-17Q UI panel: format_alignment_summary new keys
# ===========================================================================

class TestDef17QUIPanelSummary:
    """format_alignment_summary includes new Group 17Q keys."""

    _NEW_KEYS = [
        "seed_position_status",
        "corners_matched",
        "corner_position_match",
        "corner_position_color",
    ]

    def test_new_keys_present_for_none_result(self):
        summary = format_alignment_summary(None)
        for key in self._NEW_KEYS:
            assert key in summary, f"Missing key in None result: {key}"

    def test_new_keys_present_for_real_result(self):
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs=None)
        result  = align_track_model(sm, seed)
        summary = format_alignment_summary(result)
        for key in self._NEW_KEYS:
            assert key in summary, f"Missing key in real result: {key}"

    def test_seed_position_unavailable_text_when_no_defs(self):
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs=None)
        result  = align_track_model(sm, seed)
        summary = format_alignment_summary(result)
        assert "unavailable" in summary["seed_position_status"].lower()

    def test_corner_position_match_not_available_when_no_defs(self):
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs=None)
        result  = align_track_model(sm, seed)
        summary = format_alignment_summary(result)
        assert "not available" in summary["corner_position_match"].lower()

    def test_corners_matched_shows_count_when_defs_available(self):
        defs    = _make_seed_corner_defs(12)
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners, seed_pos_available=True)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs)
        result  = align_track_model(sm, seed)
        summary = format_alignment_summary(result)
        assert "12" in summary["corners_matched"], (
            f"Expected '12' in corners_matched; got: {summary['corners_matched']}"
        )

    def test_corner_position_pass_color_is_green(self):
        defs    = _make_seed_corner_defs(12)
        corners = _make_12_corners()
        sm      = _make_station_map_from_corners(corners, seed_pos_available=True)
        seed    = _make_layout_seed_with_defs(12, sm.lap_length_m, defs)
        result  = align_track_model(sm, seed)
        summary = format_alignment_summary(result)
        if result.corner_position_match == "PASS":
            assert summary["corner_position_color"] == "#88EE88"


# ===========================================================================
# DEF-17Q backward compat: accepted model JSON
# ===========================================================================

class TestDef17QBackwardCompat:
    """Accepted model JSON remains readable after Group 17Q field additions."""

    def test_export_includes_new_fields(self, tmp_path):
        r = TrackModelAlignmentResult(
            match_status           = TrackModelMatchStatus.ACCEPTABLE_MATCH,
            seed_corners_expected  = 12,
            model_corners_found    = 12,
            extra_peaks_suppressed = 24,
            placeholder_count      = 0,
            lap_length_m_model     = 5800.0,
            lap_length_m_seed      = 5792.0,
            lap_length_delta_pct   = 0.14,
            station_count          = 5354,
            confidence             = 0.87,
            corner_alignments      = [],
            sector_alignment       = SectorAlignmentResult(0, "not_available", "test"),
            blockers               = [],
            warnings               = [],
            accepted               = True,
            accepted_at            = "2026-06-26T00:00:00+00:00",
            seed_corner_positions_available = True,
            corner_position_match  = "PASS",
            corners_matched        = 12,
        )
        path = export_accepted_model_json(r, "daytona_road", "full_layout", tmp_path)
        assert path.exists()
        import json
        with open(path) as fh:
            payload = json.load(fh)
        assert "seed_corner_positions_available" in payload
        assert "corner_position_match" in payload
        assert payload["corners_matched"] == 12

    def test_import_old_json_defaults_new_fields(self, tmp_path):
        """Old accepted_model JSON without 17Q fields loads with safe defaults."""
        import json
        old_payload = {
            "schema":                 "accepted_track_model_v1",
            "track_location_id":      "daytona_road",
            "layout_id":              "full_layout",
            "match_status":           "ACCEPTABLE_MATCH",
            "accepted":               True,
            "accepted_at":            "2026-06-25T00:00:00+00:00",
            "seed_corners_expected":  12,
            "model_corners_found":    12,
            "extra_peaks_suppressed": 24,
            "placeholder_count":      0,
            "lap_length_m_model":     5800.0,
            "lap_length_m_seed":      5792.0,
            "lap_length_delta_pct":   0.14,
            "station_count":          5354,
            "confidence":             0.87,
            "blockers":               [],
            "warnings":               [],
            # NOTE: no 17Q fields — this is an old file
        }
        path = tmp_path / "daytona_road__full_layout.accepted_model.json"
        with open(path, "w") as fh:
            json.dump(old_payload, fh)
        loaded = import_accepted_model_json(path)
        assert loaded is not None
        assert loaded.seed_corner_positions_available is False
        assert loaded.corner_position_match == "NOT_AVAILABLE"
        assert loaded.corners_matched == 0
        assert loaded.accepted is True
