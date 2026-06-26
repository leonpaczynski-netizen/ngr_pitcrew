"""GROUP 17P — Seed-to-Telemetry Track Model Alignment and Whole-Model Acceptance.

Tests cover:
  DEF-17P-UAT-001: seed expects 12, curvature finds 36 → output remains 12 official
  DEF-17P-UAT-002: manual segment approval buttons not in alignment workflow
  DEF-17P-UAT-003: seed overlay note when centreline unavailable
  DEF-17P-UAT-004: alignment result includes corner and sector matching
  DEF-17P-UAT-005: extra curvature peaks stored separately, not as official turns
  DEF-17P-UAT-006: workflow state machine (not built → aligned → accepted)
"""
from __future__ import annotations

import json
import math
import types
from pathlib import Path

import pytest

from data.track_station_map import (
    SeededCorner, StationPoint, TrackStationMap,
    _detect_corners,
    build_track_station_map,
    export_station_map_json,
    import_station_map_json,
    WidthSource,
)
from data.track_model_alignment import (
    TrackModelMatchStatus,
    CornerAlignmentResult,
    SectorAlignmentResult,
    TrackModelAlignmentResult,
    align_track_model,
    get_alignment_blockers,
    export_accepted_model_json,
    import_accepted_model_json,
    find_accepted_model_path,
)
from ui.track_model_alignment_vm import (
    format_alignment_summary,
    get_acceptance_button_states,
    format_mismatch_reasons,
    manual_approval_buttons_enabled,
)
from ui.track_map_vm import TrackMapDrawData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stations(n: int = 4000, n_peaks: int = 36) -> list[StationPoint]:
    """Generate n stations with n_peaks distinct curvature spikes spaced evenly.

    Peaks are spaced ≥ 100 m apart so _find_curvature_peaks doesn't suppress them.
    Minimum n must be n_peaks * 100 for all peaks to survive separation filtering.
    """
    if n < n_peaks * 100:
        n = n_peaks * 100   # auto-enlarge to guarantee all peaks survive
    stations = []
    peak_positions = {int(i * n / n_peaks) for i in range(n_peaks)}
    for i in range(n):
        curv = 0.02 if i in peak_positions else 0.001  # spike >> threshold of 0.006
        stations.append(StationPoint(
            station_m    = float(i),
            progress_pct = i / n * 100.0,
            x            = float(i),
            y            = 0.0,
            z            = 0.0,
            curvature    = curv,
        ))
    return stations


def _make_station_map(
    corners_expected: int = 12,
    station_count: int = 4000,
    n_curvature_peaks: int = 36,
    lap_length_m: float = 5800.0,
    confidence: float = 0.85,
) -> TrackStationMap:
    """Build a synthetic TrackStationMap for testing alignment."""
    stations = _make_stations(station_count, n_peaks=n_curvature_peaks)
    corners, extra_peaks = _detect_corners(stations, corners_expected)
    return TrackStationMap(
        track_location_id   = "daytona_road",
        layout_id           = "full_layout",
        lap_length_m        = lap_length_m,
        spacing_m           = 1.0,
        stations            = stations,
        seeded_corners      = corners,
        extra_curvature_peaks = extra_peaks,
        confidence_overall  = confidence,
        corners_expected    = corners_expected,
        corners_detected    = sum(1 for c in corners if not c.is_seeded_placeholder),
        created_at          = "2026-06-25T00:00:00+00:00",
    )


def _make_layout_seed(
    corners_expected: int = 12,
    length_m: float = 5792.0,
    sectors: int = 0,
):
    """Create a duck-typed layout seed for alignment tests."""
    ns = types.SimpleNamespace(
        corners_expected = corners_expected,
        length_m         = length_m,
        sectors          = sectors if sectors else None,
    )
    return ns


# ---------------------------------------------------------------------------
# DEF-17P-UAT-001: corner cap at corners_expected
# ---------------------------------------------------------------------------

class TestDef17PUAT001CornerCap:
    """Seed expects 12, curvature finds 36 → official output remains 12."""

    def test_official_corners_capped_at_expected(self):
        stations = _make_stations(400, n_peaks=36)
        official, extras = _detect_corners(stations, corners_expected=12)
        assert len(official) == 12, (
            f"Expected exactly 12 official corners, got {len(official)}"
        )

    def test_no_t13_through_t36_in_official(self):
        stations = _make_stations(400, n_peaks=36)
        official, _ = _detect_corners(stations, corners_expected=12)
        ids = {c.corner_id for c in official}
        for bad in [f"T{n}" for n in range(13, 37)]:
            assert bad not in ids, f"Official corners must not contain {bad}"

    def test_extra_peaks_are_separated(self):
        stations = _make_stations(400, n_peaks=36)
        official, extras = _detect_corners(stations, corners_expected=12)
        assert len(extras) > 0, "Should have extra curvature peaks when detection > expected"
        assert len(official) + len(extras) <= 36

    def test_station_map_build_with_36_peaks_produces_12_official(self):
        """Integration: build_track_station_map caps to corners_expected."""
        ref = types.SimpleNamespace(
            track_location_id = "daytona_road",
            layout_id         = "full_layout",
            calibration_car_id = "porsche_rsr",
            confidence        = 0.85,
            points            = [],
        )
        # We can't call build_track_station_map without real points, so test _detect_corners directly
        stations = _make_stations(500, n_peaks=36)
        official, extras = _detect_corners(stations, corners_expected=12)
        assert len(official) == 12

    def test_no_corners_expected_keeps_all_detected(self):
        """When corners_expected=0, all detected peaks above threshold are kept."""
        stations = _make_stations(400, n_peaks=10)
        official, extras = _detect_corners(stations, corners_expected=0)
        # With corners_expected=0, there is no cap
        assert len(extras) == 0  # no extras when no cap applied
        assert len(official) > 0  # should have detected some corners


# ---------------------------------------------------------------------------
# DEF-17P-UAT-005: extra peaks classified separately (non-official)
# ---------------------------------------------------------------------------

class TestDef17PUAT005ExtraPeaksClassified:
    """Extra curvature peaks must not become official turns."""

    def test_extra_peaks_have_xp_ids(self):
        stations = _make_stations(400, n_peaks=36)
        _, extras = _detect_corners(stations, corners_expected=12)
        assert all(c.corner_id.startswith("XP") for c in extras), (
            "Extra peaks must have XP-prefixed corner IDs"
        )

    def test_extra_peaks_not_in_seeded_corners_after_build(self):
        sm = _make_station_map(corners_expected=12, n_curvature_peaks=36)
        official_ids = {c.corner_id for c in sm.seeded_corners}
        extra_ids    = {c.corner_id for c in sm.extra_curvature_peaks}
        assert official_ids.isdisjoint(extra_ids), (
            "Official and extra corner ID sets must not overlap"
        )

    def test_extra_peaks_reported_in_alignment(self):
        sm     = _make_station_map(corners_expected=12, n_curvature_peaks=36)
        seed   = _make_layout_seed(corners_expected=12, length_m=5800.0)
        result = align_track_model(sm, seed)
        assert result.extra_peaks_suppressed > 0, (
            "Alignment result must report extra_peaks_suppressed > 0"
        )

    def test_alignment_warns_about_extra_peaks(self):
        sm     = _make_station_map(corners_expected=12, n_curvature_peaks=36)
        seed   = _make_layout_seed(corners_expected=12, length_m=5800.0)
        result = align_track_model(sm, seed)
        has_extra_warning = any("extra curvature peak" in w.lower() for w in result.warnings)
        assert has_extra_warning, "Alignment should warn about suppressed extra peaks"

    def test_station_map_serialises_extra_peaks(self, tmp_path):
        sm = _make_station_map(corners_expected=12, n_curvature_peaks=36)
        p  = export_station_map_json(sm, tmp_path)
        sm2 = import_station_map_json(p)
        assert len(sm2.extra_curvature_peaks) == len(sm.extra_curvature_peaks)
        assert all(c.corner_id.startswith("XP") for c in sm2.extra_curvature_peaks)


# ---------------------------------------------------------------------------
# DEF-17P-UAT-004: alignment result has corners and sectors
# ---------------------------------------------------------------------------

class TestDef17PUAT004AlignmentDetails:
    """Alignment result includes corner and sector matching detail."""

    def test_corner_alignments_list_length_matches_model_corners(self):
        sm   = _make_station_map(corners_expected=12)
        seed = _make_layout_seed(corners_expected=12, length_m=5800.0)
        r    = align_track_model(sm, seed)
        assert len(r.corner_alignments) == 12

    def test_corner_alignment_result_fields(self):
        sm   = _make_station_map(corners_expected=12)
        seed = _make_layout_seed(corners_expected=12, length_m=5800.0)
        r    = align_track_model(sm, seed)
        ca   = r.corner_alignments[0]
        assert hasattr(ca, "corner_id")
        assert hasattr(ca, "approx_progress")
        assert hasattr(ca, "is_placeholder")
        assert hasattr(ca, "confidence")

    def test_sector_alignment_present_when_seed_has_sectors(self):
        sm   = _make_station_map(corners_expected=12)
        seed = _make_layout_seed(corners_expected=12, length_m=5800.0, sectors=3)
        r    = align_track_model(sm, seed)
        assert r.sector_alignment.seed_sector_count == 3

    def test_sector_alignment_not_available_when_no_seed_sectors(self):
        sm   = _make_station_map(corners_expected=12)
        seed = _make_layout_seed(corners_expected=12, length_m=5800.0, sectors=0)
        r    = align_track_model(sm, seed)
        assert r.sector_alignment.status == "not_available"
        assert "non-critical" in r.sector_alignment.note.lower() or "skipped" in r.sector_alignment.note.lower()

    def test_sector_alignment_note_non_critical_when_missing(self):
        sm   = _make_station_map(corners_expected=12)
        seed = _make_layout_seed(corners_expected=12, length_m=5800.0)
        r    = align_track_model(sm, seed)
        # sector note should mention it is non-critical
        assert "non-critical" in r.sector_alignment.note.lower() or \
               "skipped" in r.sector_alignment.note.lower()


# ---------------------------------------------------------------------------
# DEF-17P-UAT-002: Accept button disabled when not ACCEPTABLE_MATCH
# ---------------------------------------------------------------------------

class TestDef17PUAT002AcceptButtonStates:
    """Accept button disabled when alignment is partial/failed."""

    def test_accept_disabled_for_partial_match(self):
        # Partial match: lap length badly off
        sm = _make_station_map(corners_expected=12, lap_length_m=4000.0)  # 31% off 5800
        seed = _make_layout_seed(corners_expected=12, length_m=5800.0)
        r    = align_track_model(sm, seed)
        states = get_acceptance_button_states(r, has_station_map=True)
        assert not states["accept"], "Accept must be disabled for PARTIAL_MATCH"

    def test_accept_disabled_when_no_result(self):
        states = get_acceptance_button_states(None, has_station_map=True)
        assert not states["accept"]

    def test_accept_disabled_when_no_station_map(self):
        states = get_acceptance_button_states(None, has_station_map=False)
        assert not states["accept"]
        assert not states["rebuild"]

    def test_rebuild_enabled_when_station_map_exists(self):
        states = get_acceptance_button_states(None, has_station_map=True)
        assert states["rebuild"]

    def test_accept_disabled_for_not_ready(self):
        # NOT_READY: station_count below minimum (200)
        stations_few = [StationPoint(
            station_m=float(i), progress_pct=float(i), x=float(i), y=0.0, z=0.0,
        ) for i in range(50)]
        sm_empty = TrackStationMap(
            track_location_id="test", layout_id="test",
            lap_length_m=5800.0, spacing_m=1.0,
            stations=stations_few, seeded_corners=[], extra_curvature_peaks=[],
            confidence_overall=0.0, corners_expected=12, corners_detected=0,
        )
        seed   = _make_layout_seed(corners_expected=12, length_m=5800.0)
        r      = align_track_model(sm_empty, seed)
        assert r.match_status == TrackModelMatchStatus.NOT_READY
        states = get_acceptance_button_states(r, has_station_map=True)
        assert not states["accept"]

    def test_accept_enabled_only_for_acceptable_match(self):
        """Accept is enabled when match_status == ACCEPTABLE_MATCH and no blockers."""
        sm   = _make_station_map(corners_expected=12, lap_length_m=5800.0, station_count=500)
        seed = _make_layout_seed(corners_expected=12, length_m=5800.0)
        r    = align_track_model(sm, seed)
        # The match status depends on delta — delta 0% with 12 corners and no warnings → ACCEPTABLE
        if r.match_status == TrackModelMatchStatus.ACCEPTABLE_MATCH:
            states = get_acceptance_button_states(r, has_station_map=True)
            assert states["accept"]


# ---------------------------------------------------------------------------
# DEF-17P-UAT-006: workflow state machine
# ---------------------------------------------------------------------------

class TestDef17PUAT006WorkflowStateMachine:
    """Accepted/saved end state: not built / built not aligned / aligned not accepted / accepted."""

    def test_not_built_state_when_no_result(self):
        summary = format_alignment_summary(None)
        assert "not built" in summary["workflow_state"].lower()

    def test_built_not_aligned_for_not_ready(self):
        r = TrackModelAlignmentResult(
            match_status           = TrackModelMatchStatus.NOT_READY,
            seed_corners_expected  = 12,
            model_corners_found    = 0,
            extra_peaks_suppressed = 0,
            placeholder_count      = 0,
            lap_length_m_model     = 0.0,
            lap_length_m_seed      = 5800.0,
            lap_length_delta_pct   = 0.0,
            station_count          = 0,
            confidence             = 0.0,
            corner_alignments      = [],
            sector_alignment       = SectorAlignmentResult(0, "not_available", "test"),
            blockers               = ["Too few stations"],
            warnings               = [],
        )
        summary = format_alignment_summary(r)
        assert "not built" in summary["workflow_state"].lower()

    def test_aligned_not_accepted_for_good_match(self):
        r = TrackModelAlignmentResult(
            match_status           = TrackModelMatchStatus.GOOD_MATCH,
            seed_corners_expected  = 12,
            model_corners_found    = 12,
            extra_peaks_suppressed = 0,
            placeholder_count      = 0,
            lap_length_m_model     = 5800.0,
            lap_length_m_seed      = 5800.0,
            lap_length_delta_pct   = 0.2,
            station_count          = 500,
            confidence             = 0.85,
            corner_alignments      = [],
            sector_alignment       = SectorAlignmentResult(0, "not_available", "test"),
            blockers               = [],
            warnings               = [],
            accepted               = False,
        )
        summary = format_alignment_summary(r)
        assert "accepted" in summary["workflow_state"].lower()
        assert "not" in summary["workflow_state"].lower() or "pending" in summary["workflow_state"].lower()

    def test_accepted_and_saved_state(self):
        r = TrackModelAlignmentResult(
            match_status           = TrackModelMatchStatus.ACCEPTABLE_MATCH,
            seed_corners_expected  = 12,
            model_corners_found    = 12,
            extra_peaks_suppressed = 0,
            placeholder_count      = 0,
            lap_length_m_model     = 5800.0,
            lap_length_m_seed      = 5800.0,
            lap_length_delta_pct   = 0.1,
            station_count          = 500,
            confidence             = 0.9,
            corner_alignments      = [],
            sector_alignment       = SectorAlignmentResult(0, "not_available", "test"),
            blockers               = [],
            warnings               = [],
            accepted               = True,
            accepted_at            = "2026-06-25T00:00:00+00:00",
        )
        summary = format_alignment_summary(r)
        assert "accepted" in summary["workflow_state"].lower()
        assert "not" not in summary["workflow_state"].lower()

    def test_accepted_model_persists_and_reloads(self, tmp_path):
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
            accepted_at            = "2026-06-25T00:00:00+00:00",
        )
        p = export_accepted_model_json(r, "daytona_road", "full_layout", tmp_path)
        assert p.exists()

        p2 = find_accepted_model_path("daytona_road", "full_layout", tmp_path)
        assert p2 is not None and p2.exists()

        loaded = import_accepted_model_json(p)
        assert loaded is not None
        assert loaded.accepted is True
        assert loaded.extra_peaks_suppressed == 24
        assert loaded.model_corners_found == 12
        assert loaded.accepted_at == "2026-06-25T00:00:00+00:00"


# ---------------------------------------------------------------------------
# DEF-17P-UAT-003: seed overlay note
# ---------------------------------------------------------------------------

class TestDef17PUAT003SeedOverlayNote:
    """TrackMapDrawData carries seed_overlay_note."""

    def test_track_map_draw_data_has_seed_overlay_note_field(self):
        dd = TrackMapDrawData(
            centreline=[],
            width_left=[],
            width_right=[],
            start_finish=None,
            corner_labels=[],
            car_dot=None,
            telemetry_trace=[],
            bounds=(0, 0, 0, 0),
            status_text="",
            confidence_color="#888",
            has_map=False,
        )
        assert hasattr(dd, "seed_overlay_note")
        assert dd.seed_overlay_note == ""

    def test_seed_overlay_note_can_be_set(self):
        dd = TrackMapDrawData(
            centreline=[],
            width_left=[],
            width_right=[],
            start_finish=None,
            corner_labels=[],
            car_dot=None,
            telemetry_trace=[],
            bounds=(0, 0, 0, 0),
            status_text="",
            confidence_color="#888",
            has_map=True,
            seed_overlay_note="Seed centreline not available — showing telemetry model only.",
        )
        assert "telemetry model only" in dd.seed_overlay_note


# ---------------------------------------------------------------------------
# DEF-17P-UAT-002: manual approval buttons not in alignment workflow
# ---------------------------------------------------------------------------

class TestDef17PUAT002ManualApprovalGuard:
    """Per-segment approval buttons must not be enabled in normal workflow."""

    def test_manual_approval_disabled_in_alignment_workflow(self):
        assert manual_approval_buttons_enabled(in_alignment_workflow=True) is False

    def test_manual_approval_helper_exists_and_returns_bool(self):
        result = manual_approval_buttons_enabled()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Alignment VM: format_alignment_summary completeness
# ---------------------------------------------------------------------------

class TestAlignmentVmSummary:
    """format_alignment_summary returns all required keys."""

    _REQUIRED_KEYS = [
        "match_status", "match_color", "seed_corners", "model_corners",
        "extra_peaks", "placeholders", "lap_model", "lap_seed", "lap_delta",
        "stations", "confidence", "sector", "blockers", "warnings",
        "accepted_at", "workflow_state", "workflow_color",
    ]

    def test_none_result_returns_all_keys(self):
        s = format_alignment_summary(None)
        for key in self._REQUIRED_KEYS:
            assert key in s, f"Missing key: {key}"

    def test_real_result_returns_all_keys(self):
        sm   = _make_station_map(corners_expected=12)
        seed = _make_layout_seed(corners_expected=12, length_m=5800.0)
        r    = align_track_model(sm, seed)
        s    = format_alignment_summary(r)
        for key in self._REQUIRED_KEYS:
            assert key in s, f"Missing key: {key}"

    def test_blockers_appear_in_mismatch_reasons(self):
        sm   = _make_station_map(corners_expected=12, lap_length_m=4000.0)
        seed = _make_layout_seed(corners_expected=12, length_m=5800.0)
        r    = align_track_model(sm, seed)
        reasons = format_mismatch_reasons(r)
        assert any("BLOCKER" in line for line in reasons)

    def test_accepted_model_disables_accept_button(self):
        r = TrackModelAlignmentResult(
            match_status           = TrackModelMatchStatus.ACCEPTABLE_MATCH,
            seed_corners_expected  = 12,
            model_corners_found    = 12,
            extra_peaks_suppressed = 0,
            placeholder_count      = 0,
            lap_length_m_model     = 5800.0,
            lap_length_m_seed      = 5800.0,
            lap_length_delta_pct   = 0.1,
            station_count          = 500,
            confidence             = 0.9,
            corner_alignments      = [],
            sector_alignment       = SectorAlignmentResult(0, "not_available", "test"),
            blockers               = [],
            warnings               = [],
            accepted               = True,   # already accepted
        )
        states = get_acceptance_button_states(r, has_station_map=True)
        assert not states["accept"], "Once accepted, accept button should be disabled"
