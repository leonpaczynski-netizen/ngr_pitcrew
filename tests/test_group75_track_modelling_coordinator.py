"""UAT Finding 4 — Track Modelling state machine + geometry validation (core).

Pure, Qt-free tests of the canonical coordinator and the geometry validation
that fills the overhaul's gaps. Covers required tests:

  15. Track-model uncertainty lowers confidence and blocks corner-specific
      authoring where necessary.
  16. Track Modelling state transitions permit only legal actions.
  17. Approved track models automatically load (derive straight to ACTIVE).
"""
from __future__ import annotations

import math

import pytest

from data.track_modelling_coordinator import (
    TrackModellingCoordinator, TrackModellingState as S,
    TrackModellingAction as A, TrackModellingInputs, WorkflowStep,
    IllegalTrackModellingAction, derive_state,
)
from data.track_model_geometry_validation import validate_track_geometry


# --------------------------------------------------------------------------- #
# Test 16 — only legal actions are permitted
# --------------------------------------------------------------------------- #

def test_illegal_action_is_refused():
    coord = TrackModellingCoordinator(TrackModellingInputs(identity_known=True))
    assert coord.state is S.IDENTIFIED
    # ACTIVATE is not legal from IDENTIFIED.
    assert not coord.can(A.ACTIVATE)
    with pytest.raises(IllegalTrackModellingAction):
        coord.dispatch(A.ACTIVATE)
    # State unchanged after the refused action.
    assert coord.state is S.IDENTIFIED


def test_legal_happy_path_transitions():
    inp = TrackModellingInputs(identity_known=True)
    coord = TrackModellingCoordinator(inp)
    assert coord.state is S.IDENTIFIED

    assert coord.dispatch(A.START_CAPTURE) is S.CAPTURING
    assert coord.dispatch(A.STOP_CAPTURE) is S.CAPTURE_COMPLETE

    # BUILD_MODEL needs captured laps as a precondition.
    coord.sync_from_inputs(TrackModellingInputs(
        identity_known=True, has_captured_laps=True))
    # sync re-derives to CAPTURE_COMPLETE (has laps, no model yet)
    assert coord.state is S.CAPTURE_COMPLETE
    assert coord.can(A.BUILD_MODEL)
    assert coord.dispatch(A.BUILD_MODEL) is S.BUILDING
    assert coord.dispatch(A.BUILD_SUCCEEDED) is S.DRAFT_MODEL

    # Editing a segment (needs segments) requires the precondition.
    coord.sync_from_inputs(TrackModellingInputs(
        identity_known=True, has_captured_laps=True, has_segments=True,
        review_complete=True))
    assert coord.state is S.DRAFT_MODEL
    assert coord.dispatch(A.VALIDATE) is S.VALIDATED
    assert coord.can(A.ACTIVATE) is False  # validation not yet passed
    coord.sync_from_inputs(TrackModellingInputs(
        identity_known=True, has_segments=True, review_complete=True,
        validation_passed=True))
    assert coord.state is S.VALIDATED
    assert coord.dispatch(A.ACTIVATE) is S.ACTIVE
    assert coord.step is WorkflowStep.ACTIVATE


def test_build_model_disabled_without_evidence():
    coord = TrackModellingCoordinator(TrackModellingInputs(identity_known=True))
    coord.sync_from_inputs(TrackModellingInputs(identity_known=True))  # no laps
    # Move to CAPTURE_COMPLETE artificially is impossible without laps; assert
    # that in CAPTURE_COMPLETE without evidence BUILD is not offered.
    coord._state = S.CAPTURE_COMPLETE  # force state; inputs still lack laps
    assert not coord.can(A.BUILD_MODEL)
    with pytest.raises(IllegalTrackModellingAction):
        coord.dispatch(A.BUILD_MODEL)


def test_edit_segment_requires_segments():
    coord = TrackModellingCoordinator(TrackModellingInputs(
        identity_known=True, has_station_map=True))
    # DRAFT_MODEL but no detected segments -> EDIT_SEGMENT disabled.
    assert coord.state is S.DRAFT_MODEL
    assert not coord.can(A.EDIT_SEGMENT)


def test_error_recovery():
    coord = TrackModellingCoordinator(TrackModellingInputs(
        identity_known=True, error=True))
    assert coord.state is S.ERROR
    assert coord.can(A.RESET)
    assert coord.dispatch(A.RESET) is S.NO_TRACK


def test_select_track_always_available():
    for state in S:
        coord = TrackModellingCoordinator()
        coord._state = state
        assert coord.can(A.SELECT_TRACK), f"SELECT_TRACK missing in {state}"


# --------------------------------------------------------------------------- #
# Test 17 — approved models automatically load (derive to ACTIVE)
# --------------------------------------------------------------------------- #

def test_approved_model_auto_loads_to_active():
    inp = TrackModellingInputs(
        identity_known=True, has_reference_path=True, has_station_map=True,
        has_segments=True, review_complete=True, validation_passed=True,
        model_active=True)
    assert derive_state(inp) is S.ACTIVE
    coord = TrackModellingCoordinator(inp)
    assert coord.state is S.ACTIVE
    assert coord.step is WorkflowStep.ACTIVATE
    snap = coord.snapshot(identity_label="Fuji · Full Course", confidence="high")
    assert snap.state is S.ACTIVE
    assert "active" in snap.primary_next_step.lower()


def test_fresh_track_derives_to_identified():
    assert derive_state(TrackModellingInputs(identity_known=True)) is S.IDENTIFIED
    assert derive_state(TrackModellingInputs()) is S.NO_TRACK


def test_snapshot_lists_available_actions_only():
    coord = TrackModellingCoordinator(TrackModellingInputs(
        identity_known=True, validation_passed=True, has_segments=True,
        review_complete=True))
    snap = coord.snapshot()
    assert snap.state is S.VALIDATED
    assert A.ACTIVATE in snap.available_actions
    assert A.START_CAPTURE not in snap.available_actions


# --------------------------------------------------------------------------- #
# Test 15 — geometry uncertainty lowers confidence + blocks corner authoring
# --------------------------------------------------------------------------- #

def _circle(n=120, r=300.0):
    """A clean closed loop of n points."""
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n))
            for i in range(n)] + [(r, 0.0)]


def test_clean_geometry_high_confidence_allows_authoring():
    pts = _circle()
    res = validate_track_geometry(pts, turn_numbers=[1, 2, 3, 4],
                                  station_gap_tolerance_m=40.0)
    assert res.passed
    assert res.confidence == "high"
    assert res.closed_path_ok and res.coverage_ok and res.ordering_ok
    assert res.corner_authoring_allowed


def test_open_path_blocks_and_lowers_confidence():
    pts = _circle()[:-1]  # drop the closing point -> big open gap
    # Make it clearly open by removing the last quarter.
    pts = pts[: int(len(pts) * 0.75)]
    res = validate_track_geometry(pts, station_gap_tolerance_m=40.0)
    assert not res.passed
    assert not res.closed_path_ok
    assert res.confidence == "low"
    assert not res.corner_authoring_allowed


def test_duplicate_corner_numbers_block_authoring():
    pts = _circle()
    res = validate_track_geometry(pts, turn_numbers=[1, 2, 2, 3],
                                  station_gap_tolerance_m=40.0)
    # Duplicates are a non-blocking issue but they must lower confidence and
    # block corner-specific authoring (corner identity untrustworthy).
    assert not res.duplicates_ok
    assert res.confidence == "medium"
    assert not res.corner_authoring_allowed


def test_out_of_order_corners_block_authoring():
    pts = _circle()
    res = validate_track_geometry(pts, turn_numbers=[1, 3, 2, 4],
                                  station_gap_tolerance_m=40.0)
    assert not res.ordering_ok
    assert not res.corner_authoring_allowed


def test_coverage_gap_blocks():
    # Sparse points -> large gaps between them.
    pts = _circle(n=10, r=1000.0)
    res = validate_track_geometry(pts, station_gap_tolerance_m=25.0, min_points=10)
    assert not res.coverage_ok
    assert not res.passed
    assert not res.corner_authoring_allowed
