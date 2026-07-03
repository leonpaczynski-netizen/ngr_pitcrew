"""Group 18A — Track Truth Matcher tests.

Scenarios
---------
1. Import; no "PyQt" in matcher source.
2. Position exactly at a known station inside a corner window → station_id set,
   progress_pct matches, corner_id/sector_id populated, confidence HIGH.
3. model=None → placeholder (confidence NONE, is_usable_for_ai_corner_context False), no raise.
   Also model with empty stations → no raise.
4. validation=None → is_usable_for_ai_corner_context False.
5. Backward move (previous ~50%, candidate ~20%) → confidence not HIGH.
6. Lap wrap (previous ~98%, candidate ~2%) → NOT penalised (confidence not downgraded for wrap).
7. speed_kph=3 → pit_context set ("pit_likely" or similar) and/or warning present.
8. Far-away point (>60 m from every station) → confidence NONE, no raise.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Helper: build a simple accepted model with known stations
# ---------------------------------------------------------------------------

def _make_accepted_model():
    """Return a TrackTruthModel with known stations and a corner window.

    Stations are in strictly increasing station_m order (required for validation).
    Stations are placed along the x-axis at z=0 for easy distance calculation.
    Includes a station near progress=2% (s_wrap at station_m=20) and near 98%
    (s_end at station_m=980) for lap-wrap testing — both in monotonic order.
    """
    from data.track_truth import (
        TrackTruthManifest, TrackTruthModel,
        TrackStation, CornerWindow, SectorMarker,
    )
    manifest = TrackTruthManifest(
        track_id="test_track",
        layout_id="test_layout",
        display_name="Test",
        lap_length_m=1000.0,
        corners_expected=1,
        seed_geometry_available=True,
        corners_are_seed_verified=True,
    )
    # Stations in strictly increasing station_m order
    stations = [
        TrackStation(
            station_id="s0", station_m=0.0,   progress_pct=0.0,
            x=0.0, y=0.0, z=0.0, heading_rad=0.0,
        ),
        TrackStation(
            station_id="s_wrap", station_m=20.0, progress_pct=2.0,
            x=20.0, y=0.0, z=0.0, heading_rad=0.0,
        ),
        TrackStation(
            station_id="s1", station_m=100.0, progress_pct=10.0,
            x=100.0, y=0.0, z=0.0, heading_rad=0.0,
            corner_id="C1", corner_phase="entry", sector_id="S1",
        ),
        TrackStation(
            station_id="s2", station_m=200.0, progress_pct=20.0,
            x=200.0, y=0.0, z=0.0, heading_rad=0.0,
            corner_id="C1", corner_phase="apex", sector_id="S1",
        ),
        TrackStation(
            station_id="s3", station_m=300.0, progress_pct=30.0,
            x=300.0, y=0.0, z=0.0, heading_rad=0.0,
        ),
        # Station near progress=98% for lap-wrap test
        TrackStation(
            station_id="s_end", station_m=980.0, progress_pct=98.0,
            x=980.0, y=0.0, z=0.0, heading_rad=0.0,
        ),
    ]
    corner_windows = [
        CornerWindow(
            corner_id="C1",
            start_progress_pct=8.0,
            apex_progress_pct=15.0,
            end_progress_pct=22.0,
            sector_id="S1",
        )
    ]
    sectors = [
        SectorMarker(sector_id="S1", start_progress_pct=0.0, end_progress_pct=50.0)
    ]
    return TrackTruthModel(
        manifest=manifest,
        corner_windows=corner_windows,
        corner_complexes=[],
        sectors=sectors,
        stations=stations,
        pit_lane=None,
    )


def _make_accepted_validation(model):
    """Return a passing TrackTruthValidationResult for the given model."""
    from data.track_truth import validate_track_truth_model
    return validate_track_truth_model(model)


# ---------------------------------------------------------------------------
# Test 1 — Import and no PyQt
# ---------------------------------------------------------------------------

class TestMatcherImport:
    def test_1_import_and_no_pyqt_in_source(self):
        import pathlib
        import re
        from data.track_truth_matcher import (
            TrackTruthMatchInput,
            TrackTruthMatchResult,
            match_track_truth_position,
        )
        src = pathlib.Path("C:/Projects/VR_Dashboard/data/track_truth_matcher.py").read_text(encoding="utf-8")
        has_pyqt_import = bool(re.search(r"^\s*(import|from)\s+PyQt", src, re.MULTILINE))
        assert not has_pyqt_import, "data/track_truth_matcher.py must not import PyQt"


# ---------------------------------------------------------------------------
# Test 2 — Hit known station with corner + sector context
# ---------------------------------------------------------------------------

class TestPositionMatch:
    def test_2_known_station_high_confidence_corner_context(self):
        from data.track_truth_matcher import (
            TrackTruthMatchInput, match_track_truth_position,
        )
        from data.track_truth import TrackTruthConfidence

        model = _make_accepted_model()
        validation = _make_accepted_validation(model)

        # Position exactly at s1 (x=100, z=0, progress=10%)
        inp = TrackTruthMatchInput(
            x=100.0, y=0.0, z=0.0,
            speed_kph=120.0,
        )
        result = match_track_truth_position(inp, model, validation)

        assert result.station_id == "s1", f"Expected s1, got {result.station_id}"
        assert result.progress_pct == 10.0
        assert result.corner_id == "C1"
        assert result.sector_id == "S1"
        assert result.confidence == TrackTruthConfidence.HIGH, (
            f"Expected HIGH confidence, got {result.confidence}"
        )
        assert result.is_usable_for_ai_corner_context is True


# ---------------------------------------------------------------------------
# Test 3 — Malformed / None model
# ---------------------------------------------------------------------------

class TestMalformedInput:
    def test_3a_none_model_returns_placeholder(self):
        from data.track_truth_matcher import (
            TrackTruthMatchInput, match_track_truth_position,
        )
        from data.track_truth import TrackTruthConfidence

        inp = TrackTruthMatchInput(x=0.0, y=0.0, z=0.0)
        result = match_track_truth_position(inp, None)
        assert result.confidence == TrackTruthConfidence.NONE
        assert result.is_usable_for_ai_corner_context is False
        assert result.station_id is None

    def test_3b_empty_stations_returns_placeholder_no_raise(self):
        from data.track_truth_matcher import (
            TrackTruthMatchInput, match_track_truth_position,
        )
        from data.track_truth import (
            TrackTruthManifest, TrackTruthModel, TrackTruthConfidence,
        )
        model = TrackTruthModel(
            manifest=TrackTruthManifest(track_id="x", layout_id="y", lap_length_m=1000.0),
            stations=[],
        )
        inp = TrackTruthMatchInput(x=0.0, y=0.0, z=0.0)
        result = match_track_truth_position(inp, model)
        assert result.confidence == TrackTruthConfidence.NONE
        assert result.station_id is None


# ---------------------------------------------------------------------------
# Test 4 — validation=None → is_usable_for_ai_corner_context False
# ---------------------------------------------------------------------------

class TestValidationNone:
    def test_4_no_validation_ai_context_false(self):
        from data.track_truth_matcher import (
            TrackTruthMatchInput, match_track_truth_position,
        )
        model = _make_accepted_model()
        inp = TrackTruthMatchInput(x=100.0, y=0.0, z=0.0, speed_kph=120.0)
        result = match_track_truth_position(inp, model, validation=None)
        assert result.is_usable_for_ai_corner_context is False


# ---------------------------------------------------------------------------
# Test 5 — Backward move
# ---------------------------------------------------------------------------

class TestBackwardMove:
    def test_5_backward_progress_not_high_confidence(self):
        from data.track_truth_matcher import (
            TrackTruthMatchInput, match_track_truth_position,
        )
        from data.track_truth import TrackTruthConfidence

        model = _make_accepted_model()
        validation = _make_accepted_validation(model)

        # previous was at 50%, now matching a station at ~20% (s2, progress=20)
        # This is NOT a lap wrap (50→20), so confidence should be downgraded from HIGH
        inp = TrackTruthMatchInput(
            x=200.0, y=0.0, z=0.0,   # exactly at s2
            speed_kph=80.0,
            previous_progress_pct=50.0,
        )
        result = match_track_truth_position(inp, model, validation)
        assert result.confidence != TrackTruthConfidence.HIGH, (
            f"Backward move (50% → 20%) should downgrade from HIGH; got {result.confidence}"
        )


# ---------------------------------------------------------------------------
# Test 6 — Lap wrap (not penalised)
# ---------------------------------------------------------------------------

class TestLapWrap:
    def test_6_lap_wrap_not_penalised(self):
        from data.track_truth_matcher import (
            TrackTruthMatchInput, match_track_truth_position,
        )
        from data.track_truth import TrackTruthConfidence

        model = _make_accepted_model()
        validation = _make_accepted_validation(model)

        # previous was at 98%, candidate at ~2% — this is a lap wrap
        # Station s_wrap is at x=20, z=0, progress=2%
        inp = TrackTruthMatchInput(
            x=20.0, y=0.0, z=0.0,   # exactly at s_wrap
            speed_kph=120.0,
            previous_progress_pct=98.0,
        )
        result = match_track_truth_position(inp, model, validation)
        # Should NOT be downgraded for backward move; confidence should be HIGH (dist=0)
        assert result.confidence == TrackTruthConfidence.HIGH, (
            f"Lap wrap (98% → 2%) should not be penalised; got confidence={result.confidence}"
        )


# ---------------------------------------------------------------------------
# Test 7 — Pit (low speed)
# ---------------------------------------------------------------------------

class TestPitContext:
    def test_7_low_speed_signals_pit(self):
        from data.track_truth_matcher import (
            TrackTruthMatchInput, match_track_truth_position,
        )
        model = _make_accepted_model()
        # speed < 8 kph triggers pit_likely
        inp = TrackTruthMatchInput(
            x=0.0, y=0.0, z=0.0,
            speed_kph=3.0,
        )
        result = match_track_truth_position(inp, model)
        pit_indicated = (
            (result.pit_context is not None and "pit" in result.pit_context.lower())
            or any("pit" in w.lower() for w in result.warnings)
            or any("stop" in w.lower() for w in result.warnings)
        )
        assert pit_indicated, (
            f"Expected pit indication for speed=3 kph; "
            f"pit_context={result.pit_context!r}, warnings={result.warnings}"
        )


# ---------------------------------------------------------------------------
# Test 8 — Far-away point
# ---------------------------------------------------------------------------

class TestFarAwayPoint:
    def test_8_far_away_confidence_none_no_raise(self):
        from data.track_truth_matcher import (
            TrackTruthMatchInput, match_track_truth_position,
        )
        from data.track_truth import TrackTruthConfidence

        model = _make_accepted_model()
        # All stations are in x=[0,980], z=0. Place input 1000 m away in z.
        inp = TrackTruthMatchInput(
            x=500.0, y=0.0, z=5000.0,   # > 60 m from every station
            speed_kph=120.0,
        )
        result = match_track_truth_position(inp, model)
        assert result.confidence == TrackTruthConfidence.NONE, (
            f"Expected NONE confidence when far away; got {result.confidence}"
        )
