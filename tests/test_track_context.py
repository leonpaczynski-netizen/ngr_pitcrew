"""State Consolidation 4 — TrackContext tests.

Pure unit tests of data/track_context.py (no PyQt6, no DB, no file I/O) plus
source-scans of the track_modelling helper + migrated consumer. Mirrors
tests/test_event_context.py / test_strategy_context.py / test_setup_context.py.
"""

from pathlib import Path

import pytest

from data.event_context import build_event_context, flow_flags as event_flow_flags
from data.track_context import (
    TRACK_CONTEXT_SCHEMA,
    TrackAlignmentStatus,
    TrackContext,
    TrackContextSource,
    TrackContextValidationResult,
    TrackGeometryStatus,
    TrackIdentity,
    TrackMapAvailability,
    build_track_context,
    compute_change_hash,
    empty_track_context,
    flow_flags,
    validate_track_context,
)
from data.track_intelligence import (
    SeedAuditResult,
    SeedCornerDefinition,
    TrackLayoutSeed,
    TrackLocationSeed,
    TrackModellingStatus,
)
from data.track_calibration import TrackModelFileAudit
from data.track_model_alignment import (
    SectorAlignmentResult,
    TrackModelAlignmentResult,
    TrackModelMatchStatus,
)
from data.lap_distance_mapper import (
    LapDistanceMappingConfidence,
    LapStartOffsetCalibration,
)

ROOT = Path(__file__).parent.parent

LOC_ID = "daytona_international_speedway"
LAY_ID = "daytona_international_speedway__road_course"


@pytest.fixture(scope="module")
def tm_src():
    return (ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Fixtures using the REAL project dataclasses (no invented shapes)
# --------------------------------------------------------------------------- #
def location_seed(**over):
    d = dict(track_location_id=LOC_ID, display_name="Daytona International Speedway")
    d.update(over)
    return TrackLocationSeed(**d)


def layout_seed(**over):
    d = dict(
        layout_id=LAY_ID,
        display_name="Road Course",
        track_location_id=LOC_ID,
        length_m=5729.0,
        corners_expected=12,
        modelling_status=TrackModellingStatus.SEED_ONLY,
        corner_definitions=[
            SeedCornerDefinition(
                corner_id="T1", apex_progress_pct=8.2,
                start_progress_pct=6.0, end_progress_pct=10.0,
                direction="left", sector_id="S1",
                source="estimated", confidence="low",
            )
        ],
    )
    d.update(over)
    return TrackLayoutSeed(**d)


def seed_audit(**over):
    d = dict(has_metadata=True, has_lap_length=True, has_corner_windows=True,
             corner_count=12, seed_source="track_library")
    d.update(over)
    return SeedAuditResult(**d)


def file_audit(**over):
    d = dict(loc_id=LOC_ID, lay_id=LAY_ID, ref_path_exists=True,
             ref_path_point_count=200, calibration_laps_exists=True,
             reviewed_exists=False, offset_exists=False)
    d.update(over)
    return TrackModelFileAudit(**d)


def alignment_result(**over):
    d = dict(
        match_status=TrackModelMatchStatus.GOOD_MATCH,
        seed_corners_expected=12, model_corners_found=12,
        extra_peaks_suppressed=3, placeholder_count=0,
        lap_length_m_model=5393.0, lap_length_m_seed=5729.0,
        lap_length_delta_pct=5.1, station_count=5400, confidence=0.8,
        corner_alignments=[],
        sector_alignment=SectorAlignmentResult(3, "matched", ""),
        blockers=["lap delta"], warnings=[],
    )
    d.update(over)
    return TrackModelAlignmentResult(**d)


def offset_calibration(**over):
    d = dict(
        track_location_id=LOC_ID, layout_id=LAY_ID,
        calibration_source="zero_offset", track_length_m=5729.0,
        gt7_start_distance_m=0.0, model_start_distance_m=0.0, offset_m=0.0,
        confidence=LapDistanceMappingConfidence.LOW,
    )
    d.update(over)
    return LapStartOffsetCalibration(**d)


def make_event(**strategy_over):
    strat = {"car": "Porsche 911 RSR (991) '17",
             "track_location_id": LOC_ID, "layout_id": LAY_ID}
    strat.update(strategy_over)
    return build_event_context(
        event={"id": 7, "name": "R7", "track": "Daytona International Speedway",
               "race_type": "lap", "laps": 20},
        strategy=strat,
    )


def full_context(**over):
    kw = dict(
        selected_location_id=LOC_ID, selected_layout_id=LAY_ID,
        event_context=make_event(), location_seed=location_seed(),
        layout_seed=layout_seed(), seed_audit=seed_audit(),
        file_audit=file_audit(), alignment=alignment_result(),
        station_map_exists=True, offset_calibration=offset_calibration(),
    )
    kw.update(over)
    return build_track_context(**kw)


# --------------------------------------------------------------------------- #
# Identity resolution + sources
# --------------------------------------------------------------------------- #
class TestIdentityAndSources:
    def test_empty(self):
        ctx = build_track_context()
        assert ctx.source == TrackContextSource.EMPTY
        assert ctx.has_identity is False
        assert ctx.change_hash == ""
        assert empty_track_context().source == TrackContextSource.EMPTY

    def test_ui_selection_highest_priority(self):
        ctx = build_track_context(
            selected_location_id="ui_loc", selected_layout_id="ui_lay",
            event_context=make_event(),
            strategy={"track_location_id": "cfg_loc", "layout_id": "cfg_lay"},
        )
        assert ctx.source == TrackContextSource.TRACK_MODELLING_UI
        assert ctx.identity.track_location_id == "ui_loc"
        assert ctx.identity.layout_id == "ui_lay"

    def test_builds_from_event_context_identity(self):
        ctx = build_track_context(event_context=make_event())
        assert ctx.source == TrackContextSource.EVENT_CONTEXT
        assert ctx.identity.track_location_id == LOC_ID
        assert ctx.identity.layout_id == LAY_ID
        assert ctx.identity.track_display_name == "Daytona International Speedway"

    def test_builds_from_legacy_strategy_identity(self):
        ctx = build_track_context(
            strategy={"track": "Daytona International Speedway",
                      "track_location_id": LOC_ID, "layout_id": LAY_ID})
        assert ctx.source == TrackContextSource.LEGACY_STRATEGY
        assert ctx.identity.combined_id == f"{LOC_ID}__{LAY_ID}"

    def test_seed_only_identity(self):
        ctx = build_track_context(location_seed=location_seed(), layout_seed=layout_seed())
        assert ctx.source == TrackContextSource.SEED_LIBRARY
        assert ctx.identity.track_location_id == LOC_ID

    def test_display_names_come_from_seed(self):
        ctx = full_context()
        assert ctx.identity.track_display_name == "Daytona International Speedway"
        assert ctx.identity.layout_display_name == "Road Course"

    def test_name_only_identity_is_weak(self):
        ctx = build_track_context(strategy={"track": "Fuji Speedway"})
        assert ctx.source == TrackContextSource.LEGACY_STRATEGY
        assert ctx.is_missing_identity is True
        assert ctx.identity.combined_id == ""

    def test_combined_id(self):
        ctx = full_context()
        assert ctx.combined_id == f"{LOC_ID}__{LAY_ID}"
        assert ctx.identity.is_complete


# --------------------------------------------------------------------------- #
# Availability representation
# --------------------------------------------------------------------------- #
class TestAvailability:
    def test_seed_metadata_and_windows(self):
        av = full_context().availability
        assert av.seed_metadata_available is True
        assert av.seed_lap_length_available is True
        assert av.seed_corner_windows_available is True
        assert av.seed_corner_count == 12
        assert av.seed_source == "track_library"

    def test_seed_geometry_absent_is_false(self):
        # Daytona has no seed coordinate geometry — must be represented as
        # unavailable, never invented.
        av = full_context().availability
        assert av.seed_geometry_available is False

    def test_seed_geometry_present_when_audit_says_so(self):
        av = full_context(seed_audit=seed_audit(
            has_seed_centreline=True, centreline_point_count=500)).availability
        assert av.seed_geometry_available is True

    def test_reference_path_availability(self):
        av = full_context().availability
        assert av.reference_path_available is True
        assert av.reference_path_point_count == 200
        av2 = full_context(file_audit=file_audit(
            ref_path_exists=False, ref_path_point_count=0)).availability
        assert av2.reference_path_available is False

    def test_calibration_laps_availability(self):
        assert full_context().availability.calibration_laps_available is True

    def test_station_map_via_flag(self):
        assert full_context(station_map_exists=True).availability.station_map_available
        assert not full_context(station_map_exists=False).availability.station_map_available

    def test_station_map_via_object(self):
        class FakeStationMap:
            def station_count(self):
                return 5400
        av = full_context(station_map=FakeStationMap(),
                          station_map_exists=None).availability
        assert av.station_map_available is True
        assert av.station_map_station_count == 5400

    def test_reviewed_model_availability(self):
        assert not full_context().availability.reviewed_model_available
        assert full_context(
            file_audit=file_audit(reviewed_exists=True)
        ).availability.reviewed_model_available

    def test_accepted_model_availability(self):
        assert not full_context().availability.accepted_model_available
        ctx = full_context(alignment=alignment_result(
            accepted=True, accepted_at="2026-07-03T00:00:00Z"))
        assert ctx.availability.accepted_model_available is True

    def test_no_seed_no_files_all_false(self):
        ctx = build_track_context(selected_location_id="x", selected_layout_id="y")
        av = ctx.availability
        assert not av.seed_corner_windows_available
        assert not av.seed_geometry_available
        assert not av.reference_path_available
        assert not av.station_map_available
        assert not av.accepted_model_available


# --------------------------------------------------------------------------- #
# Geometry + modelling status + track truth gates
# --------------------------------------------------------------------------- #
class TestGeometryStatus:
    def test_modelling_status_from_seed(self):
        ctx = full_context()
        assert ctx.geometry.modelling_status == "seed_only"
        assert ctx.geometry.corners_expected == 12
        assert ctx.geometry.lap_length_seed_m == 5729.0

    def test_modelling_status_from_resolver_wins(self):
        class FakeResolved:
            modelling_status = "user_reviewed"
            ai_ready = True
            source_type = "ai_ready_reviewed_model"
        class FakeResolver:
            resolution_status = "found"
            resolved_model = FakeResolved()
        ctx = full_context(resolver_result=FakeResolver())
        assert ctx.geometry.modelling_status == "user_reviewed"
        assert ctx.geometry.ai_ready is True
        assert ctx.geometry.resolution_status == "found"
        assert ctx.geometry.model_source_type == "ai_ready_reviewed_model"

    def test_truth_gates_tristate_none_when_absent(self):
        g = full_context().geometry
        assert g.truth_accepted is None
        assert g.truth_usable_for_live_mapping is None
        assert g.truth_usable_for_ai_corner_context is None

    def test_truth_gates_echo_validation(self):
        class FakeTruthValidation:
            is_accepted = False
            is_usable_for_live_mapping = False
            is_usable_for_ai_corner_context = False
        g = full_context(truth_validation=FakeTruthValidation()).geometry
        # Daytona-style: blocked gates are echoed as False, not invented as True.
        assert g.truth_accepted is False
        assert g.truth_usable_for_live_mapping is False
        assert g.truth_usable_for_ai_corner_context is False


# --------------------------------------------------------------------------- #
# Alignment status
# --------------------------------------------------------------------------- #
class TestAlignmentStatus:
    def test_alignment_represented(self):
        al = full_context().alignment
        assert al.available is True
        assert al.match_status == "GOOD_MATCH"
        assert al.lap_length_delta_pct == 5.1
        assert al.blocker_count == 1
        assert al.accepted is False

    def test_alignment_unavailable(self):
        al = full_context(alignment=None).alignment
        assert al.available is False
        assert al.match_status == "NOT_READY"

    def test_accepted_alignment(self):
        al = full_context(alignment=alignment_result(
            accepted=True, accepted_at="2026-07-03T00:00:00Z",
            match_status=TrackModelMatchStatus.ACCEPTABLE_MATCH, blockers=[])).alignment
        assert al.accepted is True
        assert al.accepted_at == "2026-07-03T00:00:00Z"
        assert al.match_status == "ACCEPTABLE_MATCH"

    def test_garbage_alignment_not_available(self):
        al = full_context(alignment="garbage").alignment
        assert al.available is False


# --------------------------------------------------------------------------- #
# Lap offset status
# --------------------------------------------------------------------------- #
class TestLapOffset:
    def test_not_loaded(self):
        ctx = full_context(offset_calibration=None,
                           file_audit=file_audit(offset_exists=False))
        assert ctx.lap_offset_status == "not_loaded"
        assert ctx.availability.lap_offset_available is False

    def test_provisional_zero(self):
        ctx = full_context()
        assert ctx.lap_offset_status == "provisional_zero"
        assert ctx.lap_offset_confidence == "low"

    def test_calibrated(self):
        ctx = full_context(offset_calibration=offset_calibration(
            calibration_source="reference_path",
            confidence=LapDistanceMappingConfidence.MEDIUM))
        assert ctx.lap_offset_status == "calibrated"
        assert ctx.lap_offset_confidence == "medium"

    def test_on_disk_not_loaded(self):
        ctx = full_context(offset_calibration=None,
                           file_audit=file_audit(offset_exists=True))
        assert ctx.availability.lap_offset_available is True
        assert ctx.lap_offset_status == "on_disk_not_loaded"


# --------------------------------------------------------------------------- #
# Change markers
# --------------------------------------------------------------------------- #
class TestChangeMarkers:
    def test_identical_state_same_hash(self):
        assert full_context().change_hash == full_context().change_hash

    def test_hash_changes_when_identity_changes(self):
        a = full_context()
        b = full_context(selected_location_id="fuji_speedway",
                         selected_layout_id="fuji_speedway__full_course")
        assert a.change_hash != b.change_hash

    def test_hash_changes_when_availability_changes(self):
        a = full_context(station_map_exists=False)
        b = full_context(station_map_exists=True)
        assert a.change_hash != b.change_hash

    def test_hash_changes_when_alignment_changes(self):
        a = full_context()
        b = full_context(alignment=alignment_result(
            match_status=TrackModelMatchStatus.ACCEPTABLE_MATCH, blockers=[]))
        assert a.change_hash != b.change_hash

    def test_hash_ignores_event_change(self):
        # A different event (same track ids) must not change the TRACK hash —
        # event drift is tracked via event_change_hash instead.
        ev1 = make_event()
        ev2 = build_event_context(
            event={"id": 8, "name": "R8", "track": "Daytona International Speedway",
                   "race_type": "lap", "laps": 50},
            strategy={"car": "X", "track_location_id": LOC_ID, "layout_id": LAY_ID})
        a = full_context(event_context=ev1)
        b = full_context(event_context=ev2)
        assert a.change_hash == b.change_hash
        assert a.event_change_hash != b.event_change_hash

    def test_compute_change_hash_deterministic(self):
        f = {"a": 1, "b": [1, 2]}
        assert compute_change_hash(f) == compute_change_hash(dict(f))
        assert len(compute_change_hash(f)) == 12


# --------------------------------------------------------------------------- #
# Staleness / mismatch helpers
# --------------------------------------------------------------------------- #
class TestStalenessAndMismatch:
    def test_matches_event_by_ids(self):
        ctx = full_context()
        assert ctx.matches_event(make_event()) is True
        assert ctx.mismatches_event(make_event()) is False

    def test_mismatch_when_event_points_elsewhere(self):
        other_ev = build_event_context(
            event={"id": 9, "name": "R9", "track": "Fuji Speedway",
                   "race_type": "lap", "laps": 10},
            strategy={"car": "X", "track_location_id": "fuji_speedway",
                      "layout_id": "fuji_speedway__full_course"})
        ctx = full_context()
        assert ctx.matches_event(other_ev) is False
        assert ctx.mismatches_event(other_ev) is True

    def test_matches_event_tristate_none_when_uncomparable(self):
        bare_ev = build_event_context(event={"id": 1, "name": "E"})
        ctx = build_track_context(selected_location_id="x", selected_layout_id="y")
        assert ctx.matches_event(bare_ev) is None
        assert ctx.mismatches_event(bare_ev) is False  # no comparison ≠ mismatch

    def test_matches_event_by_display_name_fallback(self):
        ev = build_event_context(event={"id": 1, "name": "E", "track": "Fuji Speedway"})
        ctx = build_track_context(strategy={"track": "Fuji Speedway"})
        assert ctx.matches_event(ev) is True

    def test_is_stale_for_event(self):
        ev1 = make_event()
        ctx = full_context(event_context=ev1)
        assert ctx.is_stale_for_event(ev1) is False
        ev2 = build_event_context(
            event={"id": 7, "name": "R7", "track": "Daytona International Speedway",
                   "race_type": "lap", "laps": 55},
            strategy={"car": "X", "track_location_id": LOC_ID, "layout_id": LAY_ID})
        assert ctx.is_stale_for_event(ev2) is True

    def test_live_mapping_gate(self):
        ok = full_context(station_map_exists=True)
        assert ok.can_attempt_live_mapping is True
        assert ok.live_mapping_blockers() == ()
        no_map = full_context(station_map_exists=False)
        assert no_map.can_attempt_live_mapping is False
        assert any("station map" in b.lower() for b in no_map.live_mapping_blockers())

    def test_live_mapping_blocked_without_identity(self):
        ctx = build_track_context(strategy={"track": "Fuji Speedway"})
        assert ctx.can_attempt_live_mapping is False
        blockers = ctx.live_mapping_blockers()
        assert any("track" in b.lower() for b in blockers)
        assert any("layout" in b.lower() for b in blockers)


# --------------------------------------------------------------------------- #
# Ownership boundary — TrackContext must NOT own event/strategy/setup state
# --------------------------------------------------------------------------- #
class TestOwnershipBoundary:
    def test_no_event_race_fields(self):
        ctx = full_context()
        for name in ("race_type", "laps", "race_duration_minutes",
                     "tyre_wear_multiplier", "fuel_multiplier", "refuel_rate_lps",
                     "bop_enabled", "tuning_allowed", "allowed_tuning_categories"):
            assert not hasattr(ctx, name), f"TrackContext must not own event field {name!r}"

    def test_no_strategy_plan_fields(self):
        ctx = full_context()
        for name in ("stint_plan", "planned_stops", "fuel_burn_per_lap", "pit_laps"):
            assert not hasattr(ctx, name), f"TrackContext must not own strategy field {name!r}"

    def test_no_setup_fields(self):
        ctx = full_context()
        for name in ("adjustments", "baseline_setup", "target_setup", "purpose", "applied"):
            assert not hasattr(ctx, name), f"TrackContext must not own setup field {name!r}"

    def test_event_read_only_as_change_hash(self):
        ev = make_event()
        ctx = full_context(event_context=ev)
        assert ctx.event_change_hash == ev.change_hash
        d = ctx.to_dict()
        for k in ("race_type", "laps", "tyre_wear_multiplier", "car"):
            assert k not in d


# --------------------------------------------------------------------------- #
# Robustness — garbage never crashes
# --------------------------------------------------------------------------- #
class TestRobustness:
    def test_garbage_everything(self):
        ctx = build_track_context(
            strategy="garbage", location_seed=42, layout_seed="x",
            seed_audit=3.14, file_audit=[], resolver_result="no",
            alignment=object(), station_map_exists="weird",
            offset_calibration=None, truth_validation=123,
            event_context="not a context",
        )
        assert isinstance(ctx, TrackContext)
        # No identity from garbage → EMPTY
        assert ctx.source == TrackContextSource.EMPTY

    def test_none_everything(self):
        ctx = build_track_context(
            event_context=None, strategy=None, location_seed=None,
            layout_seed=None, seed_audit=None, file_audit=None,
            resolver_result=None, alignment=None, station_map=None,
            offset_calibration=None, truth_validation=None)
        assert ctx.source == TrackContextSource.EMPTY

    def test_validate_never_raises_on_garbage(self):
        ctx = build_track_context(strategy="junk")
        res = validate_track_context(ctx, event_context="junk")
        assert isinstance(res, TrackContextValidationResult)

    def test_broken_station_count_defensive(self):
        class Broken:
            def station_count(self):
                raise RuntimeError("boom")
        ctx = full_context(station_map=Broken(), station_map_exists=None)
        assert ctx.availability.station_map_available is True
        assert ctx.availability.station_map_station_count == 0


# --------------------------------------------------------------------------- #
# Validation — identity vs availability vs staleness separation
# --------------------------------------------------------------------------- #
class TestValidation:
    def test_empty_flagged(self):
        res = validate_track_context(empty_track_context())
        assert res.ok is False
        assert "track" in res.identity_missing

    def test_missing_layout_warns_as_identity(self):
        ctx = build_track_context(selected_location_id=LOC_ID)
        res = validate_track_context(ctx)
        assert "layout_id" in res.identity_missing
        assert any("layout" in w.lower() for w in res.identity_warnings)

    def test_missing_data_warns_as_availability(self):
        ctx = build_track_context(selected_location_id=LOC_ID,
                                  selected_layout_id=LAY_ID)
        res = validate_track_context(ctx)
        assert res.identity_warnings == ()
        assert any("reference path" in w.lower() for w in res.availability_warnings)
        assert any("station map" in w.lower() for w in res.availability_warnings)
        assert any("geometry" in w.lower() for w in res.availability_warnings)

    def test_event_mismatch_warns_as_staleness(self):
        other_ev = build_event_context(
            event={"id": 9, "name": "R9", "track": "Fuji Speedway"},
            strategy={"car": "X", "track_location_id": "fuji_speedway",
                      "layout_id": "fuji_speedway__full_course"})
        ctx = full_context()
        res = validate_track_context(ctx, event_context=other_ev)
        assert any("does not match" in w for w in res.staleness_warnings)

    def test_warnings_property_concatenates(self):
        ctx = build_track_context(selected_location_id=LOC_ID)
        res = validate_track_context(ctx)
        assert set(res.warnings) >= set(res.identity_warnings)
        assert set(res.warnings) >= set(res.availability_warnings)

    def test_fully_available_accepted_still_reports_missing_geometry_honestly(self):
        # Even a "good" Daytona context lacks seed geometry — validation must
        # keep saying so (no invented accuracy).
        ctx = full_context(alignment=alignment_result(accepted=True, blockers=[]),
                           file_audit=file_audit(reviewed_exists=True))
        res = validate_track_context(ctx)
        assert any("geometry" in w.lower() for w in res.availability_warnings)


# --------------------------------------------------------------------------- #
# Serialisation, display, flow bridge, immutability
# --------------------------------------------------------------------------- #
class TestSerialisationAndBridge:
    def test_to_dict_shape(self):
        d = full_context().to_dict()
        assert d["schema"] == TRACK_CONTEXT_SCHEMA
        assert d["source"] == "track_modelling_ui"
        assert d["identity"]["combined_id"] == f"{LOC_ID}__{LAY_ID}"
        assert d["availability"]["seed_corner_windows_available"] is True
        assert d["alignment"]["match_status"] == "GOOD_MATCH"

    def test_summary_line(self):
        line = full_context().summary_line()
        assert "Daytona International Speedway" in line
        assert "Road Course" in line
        assert "GOOD_MATCH" in line

    def test_summary_line_empty(self):
        assert "No track" in empty_track_context().summary_line()

    def test_summary_lines(self):
        lines = full_context().to_summary_lines()
        assert any("Seed:" in l for l in lines)
        assert any("Lap offset" in l for l in lines)

    def test_flow_flags_splat_safe_with_product_flow(self):
        from ui.product_flow import build_flow_state_summary
        ev = make_event()
        merged = {**event_flow_flags(ev), **flow_flags(full_context(event_context=ev))}
        summary = build_flow_state_summary(**merged)
        assert "next_action" in summary

    def test_flow_flags_empty(self):
        assert flow_flags(empty_track_context())["has_track"] is False

    def test_frozen_immutable(self):
        ctx = full_context()
        with pytest.raises(Exception):
            ctx.change_hash = "hacked"  # type: ignore[misc]
        with pytest.raises(Exception):
            ctx.identity.layout_id = "hacked"  # type: ignore[misc]
        with pytest.raises(Exception):
            ctx.availability.station_map_available = False  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Source-scan: the track_modelling helper + migrated consumer
# --------------------------------------------------------------------------- #
class TestTrackModellingMigration:
    def test_has_build_track_context_helper(self, tm_src):
        assert "def _build_track_context(self)" in tm_src
        assert "from data.track_context import build_track_context" in tm_src

    def test_helper_reads_event_context_and_existing_state(self, tm_src):
        start = tm_src.index("def _build_track_context")
        nxt = tm_src.index("\n    def ", start + 1)
        body = tm_src[start:nxt]
        assert "_build_event_context" in body
        assert "_tm_station_map" in body
        assert "_tm_alignment_result" in body
        assert "_tm_offset_calibration" in body
        assert "audit_layout_seed" in body
        assert "audit_track_model_files" in body

    def test_truth_panel_reads_identity_via_track_context(self, tm_src):
        start = tm_src.index("def _tm_refresh_track_truth_panel")
        nxt = tm_src.index("\n    def ", start + 1)
        body = tm_src[start:nxt]
        assert "_build_track_context()" in body
        assert "_last_track_context" in body
        assert "ctx.identity.track_location_id" in body
        # Behaviour preservation: only combo-sourced identity drives the panel.
        assert "TRACK_MODELLING_UI" in body

    def test_legacy_combo_writes_unchanged(self, tm_src):
        # The Group 17H config fan-out is intentionally NOT removed this sprint.
        assert 'self._config.setdefault("strategy", {})["track_location_id"]' in tm_src
        assert 'self._config.setdefault("strategy", {})["layout_id"]' in tm_src
