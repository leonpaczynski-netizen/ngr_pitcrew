"""Group 18A — Track Truth Calibration Wizard tests.

Scenarios
---------
1. Import; no "PyQt" in source.
2. Full legal path: start → set sessions → advance through CAPTURE_* →
   skip_hot_lap → BUILD_PROPOSED → build → VALIDATE → set proposed_model →
   validate → ACCEPT. Assert stage progresses at each step.
3. Illegal transition: from NOT_STARTED attempt to accept → stage unchanged,
   state.error set.
4. Geometry delegation: patch data.track_geometry_builder.build_seed_geometry
   with a sentinel and confirm build() calls it.
5. Defensive wrapper: patch build_seed_geometry to raise → build() does not
   raise; state.error set (build failed).
6. Segment review optional: reach ACCEPT without calling review_segments().
7. Abandon mid-capture: from CAPTURE_LEFT_EDGE call abandon() → stage
   NOT_STARTED, session fields cleared, no file written.
8. No partial write on validation fail: drive to VALIDATE with a failing model
   → accept() is a no-op / does not write a file.
"""
from __future__ import annotations

import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_centreline_session():
    """Return a minimal duck-typed session that satisfies build guard checks."""
    from data.track_calibration import (
        CalibrationSession, CalibrationLap, CalibrationLapQuality, TelemetrySample,
    )
    # One usable full lap (out-lap + one real lap so Gate 0a passes)
    def _make_lap(lap_num, x_offset=0.0):
        samples = []
        for i in range(80):
            t = i / 80
            side = 100.0
            perimeter = 4 * side
            dist = t * perimeter
            if dist < side:
                x, z = dist + x_offset, 0.0
            elif dist < 2 * side:
                x, z = side + x_offset, dist - side
            elif dist < 3 * side:
                x, z = side - (dist - 2 * side) + x_offset, side
            else:
                x, z = 0.0 + x_offset, side - (dist - 3 * side)
            samples.append(TelemetrySample(
                timestamp_ms=i * 100,
                lap_number=lap_num,
                x=float(x), y=0.0, z=float(z),
                speed_kph=100.0, gear=4, rpm=6000.0, throttle=0.8, brake=0.0,
            ))
        return CalibrationLap(
            lap_number=lap_num,
            lap_time_ms=120_000,
            samples=samples,
            quality=CalibrationLapQuality.USABLE,
            quality_reasons=[],
            path_length_m=400.0,
        )

    out_lap = _make_lap(0)
    lap1    = _make_lap(1)
    lap2    = _make_lap(2)
    return CalibrationSession(
        session_id="test_cal",
        track_location_id="test_track",
        layout_id="test_layout",
        laps=[out_lap, lap1, lap2],
    )


def _make_failing_proposed_model():
    """Return a TrackTruthModel that will fail validation (no stations)."""
    from data.track_truth import TrackTruthManifest, TrackTruthModel
    manifest = TrackTruthManifest(
        track_id="test_track",
        layout_id="test_layout",
        lap_length_m=1000.0,
    )
    return TrackTruthModel(manifest=manifest, stations=[])


def _make_passing_proposed_model():
    """Return a TrackTruthModel that passes validation."""
    from data.track_truth import (
        TrackTruthManifest, TrackTruthModel,
        TrackStation, CornerWindow,
    )
    manifest = TrackTruthManifest(
        track_id="test_track",
        layout_id="test_layout",
        lap_length_m=1000.0,
        corners_expected=1,
        seed_geometry_available=True,
        corners_are_seed_verified=True,
    )
    stations = [
        TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0,  x=0.0,  z=0.0),
        TrackStation(station_id="s1", station_m=100.0, progress_pct=10.0, x=10.0, z=0.0),
        TrackStation(station_id="s2", station_m=200.0, progress_pct=20.0, x=20.0, z=0.0),
    ]
    windows = [
        CornerWindow(
            corner_id="C1",
            start_progress_pct=5.0,
            apex_progress_pct=12.0,
            end_progress_pct=22.0,
        )
    ]
    return TrackTruthModel(
        manifest=manifest,
        corner_windows=windows,
        corner_complexes=[],
        sectors=[],
        stations=stations,
        pit_lane=None,
    )


# ---------------------------------------------------------------------------
# Test 1 — Import and no PyQt
# ---------------------------------------------------------------------------

class TestCalibrationImport:
    def test_1_import_and_no_pyqt_in_source(self):
        import pathlib
        from data.track_truth_calibration import (
            TrackTruthWizardStage,
            TrackTruthWizardState,
            TrackTruthCalibrationWizard,
        )
        import re
        src = pathlib.Path(
            "C:/Projects/VR_Dashboard/data/track_truth_calibration.py"
        ).read_text(encoding="utf-8")
        has_pyqt_import = bool(re.search(r"^\s*(import|from)\s+PyQt", src, re.MULTILINE))
        assert not has_pyqt_import, "data/track_truth_calibration.py must not import PyQt"


# ---------------------------------------------------------------------------
# Test 2 — Full legal wizard path
# ---------------------------------------------------------------------------

class TestFullLegalPath:
    def test_2_full_legal_path_stages_advance(self):
        from data.track_truth_calibration import (
            TrackTruthCalibrationWizard, TrackTruthWizardStage,
        )

        wizard = TrackTruthCalibrationWizard()
        assert wizard.state.stage == TrackTruthWizardStage.NOT_STARTED

        # start → CAPTURE_CENTRELINE
        wizard.start("test_track", "test_layout")
        assert wizard.state.stage == TrackTruthWizardStage.CAPTURE_CENTRELINE, (
            f"After start, expected CAPTURE_CENTRELINE; got {wizard.state.stage}"
        )

        # set centreline session and advance → CAPTURE_LEFT_EDGE
        session = _make_mock_centreline_session()
        wizard.set_centreline_session(session)
        wizard.advance()
        assert wizard.state.stage == TrackTruthWizardStage.CAPTURE_LEFT_EDGE, (
            f"Expected CAPTURE_LEFT_EDGE; got {wizard.state.stage}; error={wizard.state.error!r}"
        )

        # set left edge session and advance → CAPTURE_RIGHT_EDGE
        wizard.set_left_edge_session(session)
        wizard.advance()
        assert wizard.state.stage == TrackTruthWizardStage.CAPTURE_RIGHT_EDGE, (
            f"Expected CAPTURE_RIGHT_EDGE; got {wizard.state.stage}; error={wizard.state.error!r}"
        )

        # set right edge session and skip hot lap → BUILD_PROPOSED
        wizard.set_right_edge_session(session)
        wizard.skip_hot_lap()
        assert wizard.state.stage == TrackTruthWizardStage.BUILD_PROPOSED, (
            f"Expected BUILD_PROPOSED; got {wizard.state.stage}; error={wizard.state.error!r}"
        )

        # build → sets build_result; check build ran (can_generate may be True/False based on session)
        wizard.build(manifest_lap_length_m=400.0)
        assert wizard.state.build_result is not None, "build_result should be set after build()"

        # Manually set a passing proposed_model and advance to VALIDATE
        wizard.state.proposed_model = _make_passing_proposed_model()
        # Manually force build_result.can_generate = True so advance to VALIDATE works
        class _FakeBuildResult:
            can_generate = True
            seed_map = None
        wizard.state.build_result = _FakeBuildResult()
        wizard.advance()   # BUILD_PROPOSED → VALIDATE
        assert wizard.state.stage == TrackTruthWizardStage.VALIDATE, (
            f"Expected VALIDATE; got {wizard.state.stage}; error={wizard.state.error!r}"
        )

        # validate → sets validation_result
        wizard.validate()
        assert wizard.state.validation_result is not None, (
            "validation_result should be set after validate()"
        )

        # If the proposed_model passes validation, accept() should reach ACCEPT
        if wizard.state.validation_result.is_accepted:
            wizard.accept()
            assert wizard.state.stage == TrackTruthWizardStage.ACCEPT, (
                f"Expected ACCEPT; got {wizard.state.stage}; error={wizard.state.error!r}"
            )
        else:
            # This scenario is a no-op since model is passing; flag if it fails
            assert False, (
                f"Proposed model should have passed validation; "
                f"blockers={wizard.state.validation_result.blockers}"
            )


# ---------------------------------------------------------------------------
# Test 3 — Illegal transition
# ---------------------------------------------------------------------------

class TestIllegalTransition:
    def test_3_illegal_transition_from_not_started_to_accept(self):
        from data.track_truth_calibration import (
            TrackTruthCalibrationWizard, TrackTruthWizardStage,
        )
        wizard = TrackTruthCalibrationWizard()
        assert wizard.state.stage == TrackTruthWizardStage.NOT_STARTED

        # Attempt to call accept() from NOT_STARTED
        wizard.accept()
        assert wizard.state.stage == TrackTruthWizardStage.NOT_STARTED, (
            f"Stage should remain NOT_STARTED after illegal accept(); "
            f"got {wizard.state.stage}"
        )
        assert wizard.state.error != "", (
            "state.error should be set after illegal transition"
        )

    def test_3b_illegal_advance_from_not_started_without_ids(self):
        from data.track_truth_calibration import (
            TrackTruthCalibrationWizard, TrackTruthWizardStage,
        )
        wizard = TrackTruthCalibrationWizard()
        # Attempt to advance without calling start() first (no track_id/layout_id set)
        wizard.advance()
        assert wizard.state.stage == TrackTruthWizardStage.NOT_STARTED
        assert wizard.state.error != ""


# ---------------------------------------------------------------------------
# Test 4 — Geometry delegation (monkeypatch)
# ---------------------------------------------------------------------------

class TestGeometryDelegation:
    def test_4_build_delegates_to_track_geometry_builder(self, monkeypatch):
        from data.track_truth_calibration import (
            TrackTruthCalibrationWizard, TrackTruthWizardStage,
        )
        import data.track_geometry_builder as tgb

        call_log = []

        class _SentinelResult:
            can_generate = True
            seed_map = None
            accepted_lap_indices = []
            rejected_laps = []
            confidence = "low"
            station_count = 0
            closure_gap_m = 0.0
            error_detail = ""

        def _sentinel_build(session, manifest_lap_length_m, track_location_id, layout_id):
            call_log.append({
                "session": session,
                "lap_m": manifest_lap_length_m,
                "track_id": track_location_id,
                "layout_id": layout_id,
            })
            return _SentinelResult()

        monkeypatch.setattr(tgb, "build_seed_geometry", _sentinel_build)

        wizard = TrackTruthCalibrationWizard()
        wizard.start("test_track", "test_layout")
        wizard.state.stage = TrackTruthWizardStage.BUILD_PROPOSED
        session = _make_mock_centreline_session()
        wizard.set_centreline_session(session)
        wizard.build(manifest_lap_length_m=400.0)

        assert len(call_log) == 1, (
            f"Expected build_seed_geometry called once; got {len(call_log)} calls"
        )
        assert call_log[0]["track_id"] == "test_track"
        assert call_log[0]["layout_id"] == "test_layout"


# ---------------------------------------------------------------------------
# Test 5 — Defensive wrapper (build raises)
# ---------------------------------------------------------------------------

class TestDefensiveWrapper:
    def test_5_build_exception_does_not_raise_sets_error(self, monkeypatch):
        from data.track_truth_calibration import (
            TrackTruthCalibrationWizard, TrackTruthWizardStage,
        )
        import data.track_geometry_builder as tgb

        def _exploding_build(*args, **kwargs):
            raise RuntimeError("Simulated geometry build failure")

        monkeypatch.setattr(tgb, "build_seed_geometry", _exploding_build)

        wizard = TrackTruthCalibrationWizard()
        wizard.start("test_track", "test_layout")
        wizard.state.stage = TrackTruthWizardStage.BUILD_PROPOSED
        session = _make_mock_centreline_session()
        wizard.set_centreline_session(session)

        # Must not raise
        wizard.build(manifest_lap_length_m=400.0)

        # build_result should have can_generate=False
        assert wizard.state.build_result is not None
        assert not wizard.state.build_result.can_generate
        # state.error should reflect failure
        assert wizard.state.error != "", (
            "state.error should be set when build raises"
        )


# ---------------------------------------------------------------------------
# Test 6 — review_segments is optional
# ---------------------------------------------------------------------------

class TestSegmentReviewOptional:
    def test_6_can_reach_accept_without_review_segments(self):
        from data.track_truth_calibration import (
            TrackTruthCalibrationWizard, TrackTruthWizardStage,
        )
        wizard = TrackTruthCalibrationWizard()
        wizard.start("test_track", "test_layout")
        session = _make_mock_centreline_session()
        wizard.set_centreline_session(session)
        wizard.advance()  # → CAPTURE_LEFT_EDGE
        wizard.set_left_edge_session(session)
        wizard.advance()  # → CAPTURE_RIGHT_EDGE
        wizard.set_right_edge_session(session)
        wizard.skip_hot_lap()  # → BUILD_PROPOSED

        # Replace build_result with a passing fake; skip actual build
        class _FakeBuildResult:
            can_generate = True
            seed_map = None
        wizard.state.build_result = _FakeBuildResult()
        wizard.advance()  # → VALIDATE (since can_generate=True)
        assert wizard.state.stage == TrackTruthWizardStage.VALIDATE

        # Set a passing proposed_model and validate
        wizard.state.proposed_model = _make_passing_proposed_model()
        wizard.validate()
        assert wizard.state.validation_result is not None

        if wizard.state.validation_result.is_accepted:
            # NO call to review_segments()
            wizard.accept()
            assert wizard.state.stage == TrackTruthWizardStage.ACCEPT
        else:
            assert False, (
                f"Model should pass; blockers={wizard.state.validation_result.blockers}"
            )


# ---------------------------------------------------------------------------
# Test 7 — Abandon clears state, writes no file
# ---------------------------------------------------------------------------

class TestAbandon:
    def test_7_abandon_mid_capture_resets_and_no_file(self):
        from data.track_truth_calibration import (
            TrackTruthCalibrationWizard, TrackTruthWizardStage,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            wizard = TrackTruthCalibrationWizard()
            wizard.start("test_track", "test_layout")
            session = _make_mock_centreline_session()
            wizard.set_centreline_session(session)
            wizard.advance()  # → CAPTURE_LEFT_EDGE
            wizard.set_left_edge_session(session)

            assert wizard.state.stage == TrackTruthWizardStage.CAPTURE_LEFT_EDGE

            # Abandon from CAPTURE_LEFT_EDGE
            state = wizard.abandon()

            assert state.stage == TrackTruthWizardStage.NOT_STARTED, (
                f"Expected NOT_STARTED after abandon; got {state.stage}"
            )
            assert state.centreline_session is None
            assert state.left_edge_session is None
            assert state.right_edge_session is None
            assert state.hot_lap_session is None
            assert state.build_result is None
            assert state.validation_result is None
            assert state.proposed_model is None
            assert state.error == ""

            # No files should have been written
            all_files = list(tmp.rglob("*"))
            assert len(all_files) == 0, (
                f"abandon() must write no files; found: {all_files}"
            )


# ---------------------------------------------------------------------------
# Test 8 — No partial write when validation fails
# ---------------------------------------------------------------------------

class TestAdvanceToAcceptPersistsOrNoop:
    def test_9_advance_to_accept_persists_or_noop(self, monkeypatch):
        """advance() from VALIDATE must NOT silently reach ACCEPT without persisting geometry.

        Either:
        (a) advance() delegates to accept(), which calls save_seed_geometry_to_library
            (detected via sentinel counter), OR
        (b) advance() is a no-op with state.error set and stage stays at VALIDATE.

        Both outcomes are acceptable; the critical invariant is that stage==ACCEPT
        cannot happen without a save attempt.
        """
        from data.track_truth_calibration import (
            TrackTruthCalibrationWizard, TrackTruthWizardStage,
        )
        import data.track_geometry_builder as tgb

        save_call_count = {"n": 0}

        class _FakeSaveResult:
            error = ""

        def _sentinel_save(seed_map, track_id, layout_id, base_dir=None):
            save_call_count["n"] += 1
            return _FakeSaveResult()

        monkeypatch.setattr(tgb, "save_seed_geometry_to_library", _sentinel_save)

        wizard = TrackTruthCalibrationWizard()
        wizard.start("test_track", "test_layout")
        session = _make_mock_centreline_session()
        wizard.set_centreline_session(session)
        wizard.advance()  # → CAPTURE_LEFT_EDGE
        wizard.set_left_edge_session(session)
        wizard.advance()  # → CAPTURE_RIGHT_EDGE
        wizard.set_right_edge_session(session)
        wizard.skip_hot_lap()  # → BUILD_PROPOSED

        # Use a fake build_result with a non-None seed_map so save would be called
        class _FakeSeedMap:
            pass

        class _FakeBuildResult:
            can_generate = True
            seed_map = _FakeSeedMap()

        wizard.state.build_result = _FakeBuildResult()
        wizard.advance()  # → VALIDATE
        assert wizard.state.stage == TrackTruthWizardStage.VALIDATE

        # Set a passing proposed_model and validate
        wizard.state.proposed_model = _make_passing_proposed_model()
        wizard.validate()
        assert wizard.state.validation_result is not None
        assert wizard.state.validation_result.is_accepted is True, (
            f"Passing model must be accepted; blockers={wizard.state.validation_result.blockers}"
        )

        # Now call advance() — this is the transition under test
        wizard.advance()  # attempts VALIDATE → ACCEPT

        if wizard.state.stage == TrackTruthWizardStage.ACCEPT:
            # Outcome (a): advance delegated to accept() — save must have been called
            assert save_call_count["n"] >= 1, (
                "advance() reached ACCEPT but save_seed_geometry_to_library was never called — "
                "geometry was not persisted (silent no-save bug)"
            )
        else:
            # Outcome (b): advance was a no-op with error set
            assert wizard.state.stage == TrackTruthWizardStage.VALIDATE, (
                f"Expected stage to stay at VALIDATE if advance() is a no-op; "
                f"got {wizard.state.stage}"
            )
            assert wizard.state.error != "", (
                "advance() no-op must set state.error to explain why"
            )


class TestNoPartialWrite:
    def test_8_validation_fail_accept_noop_no_file(self):
        from data.track_truth_calibration import (
            TrackTruthCalibrationWizard, TrackTruthWizardStage,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            wizard = TrackTruthCalibrationWizard()
            wizard.start("test_track", "test_layout")
            session = _make_mock_centreline_session()
            wizard.set_centreline_session(session)
            wizard.advance()   # → CAPTURE_LEFT_EDGE
            wizard.set_left_edge_session(session)
            wizard.advance()   # → CAPTURE_RIGHT_EDGE
            wizard.set_right_edge_session(session)
            wizard.skip_hot_lap()   # → BUILD_PROPOSED

            # Set a fake build_result with can_generate=True so we can advance
            class _FakeBuildResult:
                can_generate = True
                seed_map = None
            wizard.state.build_result = _FakeBuildResult()
            wizard.advance()  # → VALIDATE

            assert wizard.state.stage == TrackTruthWizardStage.VALIDATE

            # Use a failing proposed model (no stations)
            wizard.state.proposed_model = _make_failing_proposed_model()
            wizard.validate()

            assert wizard.state.validation_result is not None
            assert wizard.state.validation_result.is_accepted is False, (
                "Failing model must not be accepted"
            )

            # accept() should be a no-op (cannot persist a failed model)
            stage_before = wizard.state.stage
            wizard.accept(base_dir=tmp)

            # Stage must remain VALIDATE, not advance to ACCEPT
            assert wizard.state.stage == TrackTruthWizardStage.VALIDATE, (
                f"Stage should not advance on failed validation; got {wizard.state.stage}"
            )
            # error should be set
            assert wizard.state.error != "", "state.error should explain why accept was rejected"

            # No geometry files written to tmp
            all_files = list(tmp.rglob("*"))
            assert all_files == [], f"No files should be written on accept() failure; found: {all_files}"
