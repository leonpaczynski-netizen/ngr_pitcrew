"""GROUP 17S — Seed Track Definition Authoring, Corner Complexes, and True Alignment Gate.

Tests:
 1. Metadata-only seed reports no corner windows and limits max status
 2. Enriched Daytona seed loads with 12 corner definitions
 3. Daytona seed has 3 sector definitions
 4. Daytona seed has 2 corner complexes
 5. T10 and T11 are both in a complex
 6. Bus Stop complex contains T1 and T2
 7. Seed audit reflects metadata, windows, sectors, complexes correctly
 8. Seed audit with no centreline always returns has_seed_centreline=False
 9. Lap delta 5.1% creates a BLOCKER (not just a warning)
10. Lap delta > 20% creates a CRITICAL blocker
11. Lap delta < 5% produces no blocker
12. Straight at 0–7.3% progress is NOT assigned to T2 when seed windows are present
13. Segment midpoint at 8.2% (inside T1 window 5.5–11%) IS assigned T1
14. format_seed_audit_summary metadata-only
15. format_seed_audit_summary with windows, sectors, complexes
16. Legacy warning filter pattern matches expected strings
17. audit_layout_seed(None) returns has_metadata=False
18. SeedSectorDefinition parses from dict
19. CornerComplexDefinition parses from dict
20. format_alignment_summary includes seed_audit key
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

# ── imports from the project ──────────────────────────────────────────────────
from data.track_intelligence import (
    load_track_seed,
    resolve_track_layout,
    audit_layout_seed,
    SeedSectorDefinition,
    CornerComplexDefinition,
    SeedAuditResult,
    SeedCornerDefinition,
    TrackLayoutSeed,
    TrackModellingStatus,
)
from data.track_model_alignment import (
    align_track_model,
    TrackModelMatchStatus,
    SectorAlignmentResult,
    CornerAlignmentResult,
    TrackModelAlignmentResult,
)
from ui.track_model_alignment_vm import (
    format_alignment_summary,
    format_seed_audit_summary,
)
from data.seed_corner_matching import CornerMatchStatus, CornerCandidateMatch


# ── Helper: build a minimal TrackStationMap mock ──────────────────────────────

@dataclass
class _MockSeededCorner:
    corner_id: str
    approx_progress: float
    is_seeded_placeholder: bool = False
    confidence: float = 0.8


@dataclass
class _MockStationMap:
    lap_length_m: float
    confidence_overall: float
    track_location_id: str = "mock_loc"
    layout_id: str = "mock_lay"
    seeded_corners: list = field(default_factory=list)
    extra_curvature_peaks: list = field(default_factory=list)

    def station_count(self) -> int:
        return 5500   # above MIN_STATIONS_FOR_ALIGNMENT (200)


def _make_seed(
    length_m: float = 5729.0,
    corners_expected: int = 12,
    corner_defs: list = None,
    sector_defs: list = None,
    complexes: list = None,
):
    return TrackLayoutSeed(
        layout_id         = "test_layout",
        display_name      = "Test Layout",
        track_location_id = "test_loc",
        length_m          = length_m,
        corners_expected  = corners_expected,
        corner_definitions= corner_defs or [],
        sector_definitions= sector_defs or [],
        corner_complexes  = complexes or [],
        modelling_status  = TrackModellingStatus.NOT_MODELLED,
    )


def _assign_turn_from_seed_windows(mid_progress: float, corner_defs) -> Optional[str]:
    """Pure logic for seed-window-based turn assignment (mirrors dashboard._tm_refresh_seg_table)."""
    for cdef in corner_defs:
        w_start = cdef.start_progress_pct / 100.0
        w_end   = cdef.end_progress_pct   / 100.0
        if w_start <= mid_progress <= w_end:
            return cdef.corner_id
    return None


# ── Test 1: metadata-only seed has no corner windows ─────────────────────────

def test_metadata_only_seed_has_no_corner_windows():
    seed = _make_seed(corner_defs=[])
    audit = audit_layout_seed(seed)
    assert audit.has_corner_windows is False
    assert audit.corner_count == 0


def test_metadata_only_seed_max_status_is_good_match():
    seed = _make_seed(corner_defs=[])
    audit = audit_layout_seed(seed)
    assert audit.max_match_status == "GOOD_MATCH"


# ── Test 2: enriched Daytona seed loads with 12 corner definitions ────────────

def test_daytona_seed_loads_with_12_corner_windows():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    assert seed is not None, "Daytona Road Course layout not found in YAML"
    assert len(seed.corner_definitions) == 12, (
        f"Expected 12 corner definitions, got {len(seed.corner_definitions)}"
    )


def test_daytona_corner_ids_t1_through_t12():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    ids = {c.corner_id for c in seed.corner_definitions}
    for expected in ("T1", "T2", "T3", "T10", "T11", "T12"):
        assert expected in ids, f"Corner {expected} missing from Daytona seed"


# ── Test 3: Daytona seed has 3 sector definitions ─────────────────────────────

def test_daytona_seed_has_3_sectors():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    assert len(seed.sector_definitions) == 3, (
        f"Expected 3 sector definitions, got {len(seed.sector_definitions)}"
    )


def test_daytona_sector_ids():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    sector_ids = {s.sector_id for s in seed.sector_definitions}
    assert "S1" in sector_ids
    assert "S2" in sector_ids
    assert "S3" in sector_ids


# ── Test 4: Daytona seed has 2 corner complexes ───────────────────────────────

def test_daytona_seed_has_2_complexes():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    assert len(seed.corner_complexes) == 2, (
        f"Expected 2 corner complexes, got {len(seed.corner_complexes)}"
    )


# ── Test 5: T10 and T11 are in a complex ─────────────────────────────────────

def test_t10_t11_grouped_in_complex():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    members_in_complexes: set[str] = set()
    for cx in seed.corner_complexes:
        members_in_complexes.update(cx.member_corner_ids)
    assert "T10" in members_in_complexes, "T10 not in any complex"
    assert "T11" in members_in_complexes, "T11 not in any complex"


def test_t10_t11_share_the_same_complex():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    for cx in seed.corner_complexes:
        if "T10" in cx.member_corner_ids and "T11" in cx.member_corner_ids:
            return  # found both in the same complex
    pytest.fail("T10 and T11 are not together in the same complex")


# ── Test 6: Bus Stop complex contains T1 and T2 ───────────────────────────────

def test_bus_stop_complex_contains_t1_and_t2():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    for cx in seed.corner_complexes:
        if "T1" in cx.member_corner_ids and "T2" in cx.member_corner_ids:
            return
    pytest.fail("No complex found containing both T1 and T2")


# ── Test 7: audit_layout_seed with full Daytona data ─────────────────────────

def test_audit_daytona_seed_has_all_fields():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    audit = audit_layout_seed(seed)
    assert audit.has_metadata is True
    assert audit.has_lap_length is True
    assert audit.has_sector_definitions is True
    assert audit.has_corner_windows is True
    assert audit.has_corner_complexes is True
    assert audit.corner_count == 12
    assert audit.sector_count == 3
    assert audit.complex_count == 2
    assert audit.max_match_status == "ACCEPTABLE_MATCH"


# ── Test 8: seed centreline always False ─────────────────────────────────────

def test_seed_centreline_always_unavailable():
    seed = _make_seed()
    audit = audit_layout_seed(seed)
    assert audit.has_seed_centreline is False
    assert audit.centreline_point_count == 0


def test_daytona_seed_centreline_unavailable():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    audit = audit_layout_seed(seed)
    assert audit.has_seed_centreline is False


# ── Test 9: lap delta 8.1% creates a BLOCKER (threshold raised to 8% in Group 23A) ────

def test_lap_delta_5pct_creates_blocker():
    # Group 23A: threshold raised to 8%.  Use 8.1% delta to trigger the blocker.
    # Model 5263 m vs seed 5729 m ≈ 8.13% delta
    seed = _make_seed(length_m=5729.0)
    sm = _MockStationMap(
        lap_length_m=5263.0,
        confidence_overall=0.85,
        seeded_corners=[],   # no corners, so corner count mismatch blocker also fires
    )
    result = align_track_model(sm, seed)
    # Check that at least one blocker mentions lap length / mismatch
    lap_blockers = [b for b in result.blockers if "Lap length mismatch" in b or "lap" in b.lower()]
    assert lap_blockers, (
        f"Expected a lap-length blocker for 8.1% delta, got blockers: {result.blockers}"
    )


def test_lap_delta_5pct_match_status_is_partial():
    # Group 23A: 5.1% delta is now within GOOD_MATCH threshold (8%).
    # Use 8.1% delta to verify PARTIAL_MATCH behaviour is still triggered.
    seed = _make_seed(length_m=5729.0, corners_expected=0)
    sm = _MockStationMap(
        lap_length_m=5263.0,
        confidence_overall=0.85,
        seeded_corners=[],
    )
    result = align_track_model(sm, seed)
    # 8.1% delta → blockers exist → PARTIAL_MATCH
    assert result.match_status == TrackModelMatchStatus.PARTIAL_MATCH


# ── Test 10: lap delta > 20% creates a critical blocker ──────────────────────

def test_lap_delta_over_20pct_creates_critical_blocker():
    seed = _make_seed(length_m=5729.0, corners_expected=0)
    sm = _MockStationMap(
        lap_length_m=3000.0,   # ~47.7% delta
        confidence_overall=0.85,
        seeded_corners=[],
    )
    result = align_track_model(sm, seed)
    lap_blockers = [b for b in result.blockers if "lap" in b.lower() or "Lap" in b]
    assert lap_blockers, "Expected critical lap blocker for >20% delta"
    assert result.match_status in (
        TrackModelMatchStatus.FAILED_MATCH, TrackModelMatchStatus.PARTIAL_MATCH
    )


# ── Test 11: lap delta < 5% produces no lap blocker ──────────────────────────

def test_lap_delta_under_5pct_no_lap_blocker():
    seed = _make_seed(length_m=5729.0, corners_expected=0)
    sm = _MockStationMap(
        lap_length_m=5700.0,   # ~0.5% delta
        confidence_overall=0.85,
        seeded_corners=[],
    )
    result = align_track_model(sm, seed)
    lap_blockers = [b for b in result.blockers if "Lap length mismatch" in b]
    assert not lap_blockers, f"Unexpected lap blocker for <5% delta: {lap_blockers}"


# ── Test 12: straight at 0–7.3% NOT assigned to T2 ───────────────────────────

def test_straight_before_t1_not_assigned_t2():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    corner_defs = seed.corner_definitions

    # The pre-T1 straight has midpoint around 3.65% (0–7.3% range)
    mid = 0.0365
    assigned = _assign_turn_from_seed_windows(mid, corner_defs)

    # T2 window starts at 11%, so 3.65% should not be assigned T2
    assert assigned != "T2", (
        f"Pre-T1 straight at {mid:.1%} was incorrectly assigned to T2"
    )


def test_straight_before_t1_gets_no_assignment():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    # T1 window starts at 5.5%, so the 0–5.5% gap is unassigned
    mid = 0.03   # 3% — entirely in the pre-corner straight
    assigned = _assign_turn_from_seed_windows(mid, seed.corner_definitions)
    assert assigned is None, (
        f"Expected no assignment for 3% progress (before T1 window), got {assigned}"
    )


# ── Test 13: segment at 8.2% assigned T1 ─────────────────────────────────────

def test_segment_at_8pct_assigned_t1():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    # T1 window: 5.5% – 11%, apex 8.2%
    mid = 0.082   # 8.2%
    assigned = _assign_turn_from_seed_windows(mid, seed.corner_definitions)
    assert assigned == "T1", f"Expected T1 assignment at 8.2%, got {assigned}"


def test_segment_at_t1_window_start_edge():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    # Exactly at window start boundary — 5.5%
    mid = 0.055
    assigned = _assign_turn_from_seed_windows(mid, seed.corner_definitions)
    assert assigned == "T1", f"Expected T1 at window start, got {assigned}"


def test_segment_at_t11_window_assigned_t11():
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    # T11 window: 79%–85.5%, apex 82%
    mid = 0.82
    assigned = _assign_turn_from_seed_windows(mid, seed.corner_definitions)
    assert assigned == "T11", f"Expected T11 at 82%, got {assigned}"


# ── Test 14: format_seed_audit_summary metadata-only ─────────────────────────

def test_format_seed_audit_metadata_only():
    audit = SeedAuditResult(
        has_metadata=True,
        has_lap_length=True,
        has_sector_definitions=False,
        has_corner_windows=False,
        has_corner_complexes=False,
        has_seed_centreline=False,
        corner_count=0,
        sector_count=0,
        complex_count=0,
    )
    result = format_seed_audit_summary(audit)
    assert "lap length" in result
    assert "corner windows" not in result
    assert "no centreline" in result


def test_format_seed_audit_none_returns_dash():
    assert format_seed_audit_summary(None) == "—"


# ── Test 15: format_seed_audit_summary with full Daytona data ─────────────────

def test_format_seed_audit_summary_with_all_fields():
    audit = SeedAuditResult(
        has_metadata=True,
        has_lap_length=True,
        has_sector_definitions=True,
        has_corner_windows=True,
        has_corner_complexes=True,
        has_seed_centreline=False,
        corner_count=12,
        sector_count=3,
        complex_count=2,
    )
    result = format_seed_audit_summary(audit)
    assert "12 corner windows" in result
    assert "3 sectors" in result
    assert "2 complexes" in result
    assert "no centreline" in result


# ── Test 16: legacy warning filter patterns ───────────────────────────────────

def test_legacy_warning_filter_corner_count_mismatch():
    warns = [
        "Corner count mismatch: model has 5, seed expects 12",
        "Reference path confidence 0.55 is below 0.60",
    ]
    filtered = [
        w for w in warns
        if "Corner count mismatch" not in w
        and "corners vs expected" not in w
    ]
    assert len(filtered) == 1
    assert "confidence" in filtered[0]


def test_legacy_warning_filter_corners_vs_expected():
    warns = [
        "Detected 5 corners vs expected 12 (difference 7) — missing corners may need more calibration laps",
        "Some other warning",
    ]
    filtered = [
        w for w in warns
        if "Corner count mismatch" not in w
        and "corners vs expected" not in w
    ]
    assert len(filtered) == 1
    assert "Some other warning" in filtered[0]


# ── Test 17: audit_layout_seed(None) ─────────────────────────────────────────

def test_audit_none_seed():
    audit = audit_layout_seed(None)
    assert audit.has_metadata is False
    assert audit.missing_for_full_accept != []


# ── Test 18: SeedSectorDefinition parses from dict ───────────────────────────

def test_seed_sector_definition_fields():
    sd = SeedSectorDefinition(
        sector_id="S1",
        display_name="Sector 1",
        start_progress_pct=0.0,
        end_progress_pct=33.0,
        source="estimated",
        confidence="low",
    )
    assert sd.sector_id == "S1"
    assert sd.end_progress_pct == 33.0
    assert sd.source == "estimated"


# ── Test 19: CornerComplexDefinition parses from dict ────────────────────────

def test_corner_complex_definition_fields():
    cx = CornerComplexDefinition(
        complex_id="T10T11",
        display_name="T10/T11 Complex",
        member_corner_ids=["T10", "T11"],
        start_progress_pct=73.0,
        end_progress_pct=85.5,
        sector_id="S3",
        coaching_name="Horseshoe",
        notes="T10 and T11 are connected",
        source="estimated",
        confidence="low",
    )
    assert cx.complex_id == "T10T11"
    assert "T10" in cx.member_corner_ids
    assert "T11" in cx.member_corner_ids
    assert cx.coaching_name == "Horseshoe"


# ── Test 20: format_alignment_summary includes seed_audit key ────────────────

def test_format_alignment_summary_none_includes_seed_audit():
    summary = format_alignment_summary(None)
    assert "seed_audit" in summary
    assert summary["seed_audit"] == "—"


def test_format_alignment_summary_with_result_includes_seed_audit():
    from data.seed_corner_matching import CornerMatchStatus
    result = TrackModelAlignmentResult(
        match_status           = TrackModelMatchStatus.GOOD_MATCH,
        seed_corners_expected  = 0,
        model_corners_found    = 0,
        extra_peaks_suppressed = 0,
        placeholder_count      = 0,
        lap_length_m_model     = 5800.0,
        lap_length_m_seed      = 5800.0,
        lap_length_delta_pct   = 0.0,
        station_count          = 5800,
        confidence             = 0.85,
        corner_alignments      = [],
        sector_alignment       = SectorAlignmentResult(
            seed_sector_count=0, status="not_available", note=""),
        blockers               = [],
        warnings               = [],
        seed_corner_positions_available = False,
        corner_position_match  = "NOT_AVAILABLE",
        corners_matched        = 0,
        corner_candidate_matches = [],
    )
    summary = format_alignment_summary(result)
    assert "seed_audit" in summary
    # When no layout_seed passed, audit is computed for None
    assert isinstance(summary["seed_audit"], str)


def test_format_alignment_summary_with_layout_seed():
    from data.seed_corner_matching import CornerMatchStatus
    result = TrackModelAlignmentResult(
        match_status           = TrackModelMatchStatus.GOOD_MATCH,
        seed_corners_expected  = 12,
        model_corners_found    = 12,
        extra_peaks_suppressed = 0,
        placeholder_count      = 0,
        lap_length_m_model     = 5800.0,
        lap_length_m_seed      = 5729.0,
        lap_length_delta_pct   = 1.2,
        station_count          = 5800,
        confidence             = 0.85,
        corner_alignments      = [],
        sector_alignment       = SectorAlignmentResult(
            seed_sector_count=3, status="not_available", note=""),
        blockers               = [],
        warnings               = [],
        seed_corner_positions_available = True,
        corner_position_match  = "PASS",
        corners_matched        = 12,
        corner_candidate_matches = [],
    )
    seed = resolve_track_layout(
        "daytona_international_speedway",
        "daytona_international_speedway__road_course",
    )
    summary = format_alignment_summary(result, layout_seed=seed)
    # Should show corner windows and sectors in audit string
    assert "12 corner windows" in summary["seed_audit"]
    assert "3 sectors" in summary["seed_audit"]


# ── Regression: existing seed load still works without new fields ─────────────

def test_seed_load_success():
    result = load_track_seed()
    assert result.success, f"Seed failed to load: {result.errors}"


def test_layouts_without_corners_still_load():
    """Seeds that have no corners: key should yield empty corner_definitions."""
    result = load_track_seed()
    locations_without_corners = [
        layout
        for loc in result.track_locations
        for layout in loc.layouts
        if not layout.corner_definitions
    ]
    # Many layouts in seed have no corners — this must not cause load failure
    assert result.success
    assert len(locations_without_corners) > 0   # confirms backward compat


def test_layouts_without_sectors_have_empty_list():
    result = load_track_seed()
    # Any layout that had no sector_definitions: key must return []
    for loc in result.track_locations:
        for layout in loc.layouts:
            assert isinstance(layout.sector_definitions, list)
            assert isinstance(layout.corner_complexes, list)
