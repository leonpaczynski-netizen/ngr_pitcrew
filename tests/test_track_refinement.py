"""Tests for data/track_refinement.py (continuous refinement, Phase 1).

Covers the safety-critical parts: the non-regression/improvement gate,
candidate persistence round-trip, the ledger, and gated promotion (never
promote a worse candidate; reject a stale base).
"""
from __future__ import annotations

import json

import pytest

from data.track_model_alignment import (
    SectorAlignmentResult,
    TrackModelAlignmentResult,
    TrackModelMatchStatus,
    export_accepted_model_json,
    find_accepted_model_path,
    import_accepted_model_json,
)
from types import SimpleNamespace

from data.track_refinement import (
    compare_models,
    export_candidate_model_json,
    import_candidate_alignment,
    find_candidate_model_path,
    append_refinement_ledger,
    refinement_ledger_filename,
    refine_from_session,
    promote_candidate,
    discard_candidate,
    mean_path_shift_m,
    export_candidate_reference_path,
    find_candidate_reference_path,
    blend_reference_path,
    MAX_MEAN_SHIFT_M,
    EVENT_WEIGHT_DEFAULT,
)
from data.track_calibration import ReferencePath, ReferencePathPoint


def _pts(coords):
    """Build reference-path-like points from a list of (x, y, z)."""
    return [SimpleNamespace(x=x, y=y, z=z) for (x, y, z) in coords]


def _refpath(coords):
    """Build a ReferencePath from a list of (x, y, z)."""
    n = len(coords)
    pts = [
        ReferencePathPoint(
            lap_progress=(i / (n - 1)) if n > 1 else 0.0,
            distance_along_lap_m=float(i),
            x=x, y=y, z=z, speed_kph_avg=120.0, source_lap_count=3,
        )
        for i, (x, y, z) in enumerate(coords)
    ]
    return ReferencePath(
        track_location_id="fuji", layout_id="fuji__full_course",
        calibration_car_id="rsr", source_lap_count=3, points=pts, confidence=0.9,
    )

LOC = "fuji"
LAY = "fuji__full_course"


def _mk_align(**over) -> TrackModelAlignmentResult:
    base = dict(
        match_status=TrackModelMatchStatus.GOOD_MATCH,
        seed_corners_expected=16,
        model_corners_found=16,
        extra_peaks_suppressed=0,
        placeholder_count=0,
        lap_length_m_model=4440.0,
        lap_length_m_seed=4563.0,
        lap_length_delta_pct=2.68,
        station_count=4441,
        confidence=1.0,
        corner_alignments=[],
        sector_alignment=SectorAlignmentResult(0, "not_available", ""),
        blockers=[],
        warnings=[],
        accepted=True,
        accepted_at="2026-07-12T09:00:00+00:00",
    )
    base.update(over)
    return TrackModelAlignmentResult(**base)


# -------------------------------------------------- Phase 2·0 geometry guard

def test_mean_path_shift_identical_is_zero():
    pts = [(i * 1.0, 0.0, i * 2.0) for i in range(300)]
    assert mean_path_shift_m(_pts(pts), _pts(pts)) == pytest.approx(0.0, abs=1e-9)


def test_mean_path_shift_offset_measured():
    a = [(i * 1.0, 0.0, 0.0) for i in range(300)]
    b = [(i * 1.0, 0.0, 5.0) for i in range(300)]  # shifted 5 m in z
    assert mean_path_shift_m(_pts(a), _pts(b)) == pytest.approx(5.0, abs=1e-6)


def test_mean_path_shift_none_when_too_short():
    assert mean_path_shift_m(_pts([(0, 0, 0)]), _pts([(1, 1, 1), (2, 2, 2)])) is None


def test_gate_large_geometry_shift_blocks_even_with_improvement():
    accepted = _mk_align(model_corners_found=15)
    candidate = _mk_align(model_corners_found=16)  # would improve
    v = compare_models(accepted, candidate, geometry_shift_m=MAX_MEAN_SHIFT_M + 2.0)
    assert v.improves is False
    assert any("shifted" in r for r in v.regression_reasons)


def test_gate_small_geometry_shift_allows_improvement():
    accepted = _mk_align(model_corners_found=15)
    candidate = _mk_align(model_corners_found=16)
    v = compare_models(accepted, candidate, geometry_shift_m=1.0)
    assert v.improves is True
    assert v.regression_reasons == []


def test_candidate_reference_path_persist_and_cleanup(tmp_path):
    rp = SimpleNamespace(points=_pts([(i, 0.0, i) for i in range(50)]))
    path = export_candidate_reference_path(rp, LOC, LAY, output_dir=tmp_path)
    assert path is not None and path.exists()
    assert find_candidate_reference_path(LOC, LAY, base_dir=tmp_path) is not None
    # A candidate model + its companion are both cleared on discard.
    export_candidate_model_json(_mk_align(accepted=False), LOC, LAY, {}, output_dir=tmp_path)
    assert discard_candidate(LOC, LAY, models_dir=tmp_path) is True
    assert find_candidate_reference_path(LOC, LAY, base_dir=tmp_path) is None


def test_promote_refused_on_large_stored_shift(tmp_path):
    _write_accepted(tmp_path, model_corners_found=15, accepted_at="T1")
    cand = _mk_align(model_corners_found=16, accepted=False)  # metrics improve
    export_candidate_model_json(
        cand, LOC, LAY,
        {"base_accepted_at": "T1", "geometry_shift_m": MAX_MEAN_SHIFT_M + 5.0},
        output_dir=tmp_path,
    )
    # Re-check at promote applies the stored shift → blocked despite better metrics.
    assert promote_candidate(LOC, LAY, models_dir=tmp_path) is None
    assert find_candidate_model_path(LOC, LAY, base_dir=tmp_path) is not None


# ------------------------------------------------ Phase 2C reviewed-segments

def _stage_a_review(models_dir, n_segments, loc=LOC, lay=LAY):
    """Write a staged (pending) reviewed-segments file with n_segments segments."""
    from data.track_segment_review import (
        TrackModelReviewResult, ReviewedTrackSegment, SegmentReviewStatus, export_review_json,
    )
    from data.track_segment_detection import TrackSegmentType, TrackSegmentDetectionConfidence
    segs = [
        ReviewedTrackSegment(
            segment_id=f"S{i}", segment_type=TrackSegmentType.APEX_ZONE,
            original_display_name=f"Turn {i}",
            lap_progress_start=i / n_segments, lap_progress_end=(i + 0.4) / n_segments,
            lap_progress_mid=(i + 0.2) / n_segments,
            confidence=TrackSegmentDetectionConfidence.HIGH,
            review_status=SegmentReviewStatus.CONFIRMED,
        )
        for i in range(n_segments)
    ]
    review = TrackModelReviewResult(
        track_location_id=loc, layout_id=lay, calibration_car_id="rsr",
        source_lap_count=3, detected_corner_count=n_segments, expected_corner_count=n_segments,
        detection_confidence=TrackSegmentDetectionConfidence.HIGH, segments=segs,
    )
    from pathlib import Path as _P
    return export_review_json(review, output_dir=_P(models_dir) / "_refine_pending", session_id="pending")


def test_publish_staged_review_makes_it_resolver_visible(tmp_path):
    from data.track_refinement import _publish_staged_review
    from data.track_model_resolver import find_reviewed_models_for_layout
    _stage_a_review(tmp_path, n_segments=16)
    # Staged file is NOT resolver-visible (it lives in the _refine_pending subdir).
    assert find_reviewed_models_for_layout(LOC, LAY, base_dir=tmp_path) == []
    ok = _publish_staged_review(LOC, LAY, tmp_path, min_segments=16)
    assert ok is True
    published = find_reviewed_models_for_layout(LOC, LAY, base_dir=tmp_path)
    assert len(published) == 1
    assert "_refine_pending" not in str(published[0])


def test_publish_refused_when_would_downgrade_segments(tmp_path):
    from data.track_refinement import _publish_staged_review
    from data.track_model_resolver import find_reviewed_models_for_layout
    _stage_a_review(tmp_path, n_segments=10)  # fewer than the model's 16 corners
    ok = _publish_staged_review(LOC, LAY, tmp_path, min_segments=16)
    assert ok is False
    assert find_reviewed_models_for_layout(LOC, LAY, base_dir=tmp_path) == []


def test_publish_noop_when_nothing_staged(tmp_path):
    from data.track_refinement import _publish_staged_review
    assert _publish_staged_review(LOC, LAY, tmp_path, min_segments=0) is False


def test_discard_removes_staged_review(tmp_path):
    from data.track_refinement import _staged_review_path
    _stage_a_review(tmp_path, n_segments=16)
    export_candidate_model_json(_mk_align(accepted=False), LOC, LAY, {}, output_dir=tmp_path)
    assert _staged_review_path(LOC, LAY, tmp_path).exists()
    assert discard_candidate(LOC, LAY, models_dir=tmp_path) is True
    assert not _staged_review_path(LOC, LAY, tmp_path).exists()


# ------------------------------------------------ Phase 2B weighted anchoring

def test_blend_caps_event_influence_at_weight():
    # Candidate 10 m off the accepted path; blend at 0.30 → 3 m off (30%).
    cand = _refpath([(10.0, 0.0, 0.0) for _ in range(100)])
    acc = [(0.0, 0.0, 0.0) for _ in range(100)]
    blended = blend_reference_path(cand, acc, 0.30)
    assert blended.points[0].x == pytest.approx(3.0, abs=1e-6)
    assert blended.points[50].x == pytest.approx(3.0, abs=1e-6)


def test_blend_weight_zero_yields_accepted():
    cand = _refpath([(10.0, 0.0, 5.0) for _ in range(100)])
    acc = [(0.0, 0.0, 0.0) for _ in range(100)]
    blended = blend_reference_path(cand, acc, 0.0)
    assert blended.points[0].x == pytest.approx(0.0, abs=1e-6)
    assert blended.points[0].z == pytest.approx(0.0, abs=1e-6)


def test_blend_no_accepted_returns_unchanged():
    cand = _refpath([(10.0, 0.0, 0.0) for _ in range(100)])
    assert blend_reference_path(cand, [], 0.30) is cand


def test_blend_reduces_geometry_shift_proportionally():
    cand = _refpath([(i * 1.0, 0.0, 10.0) for i in range(200)])   # 10 m off in z
    acc = [(i * 1.0, 0.0, 0.0) for i in range(200)]
    raw_shift = mean_path_shift_m(acc, _pts([(p.x, p.y, p.z) for p in cand.points]))
    blended = blend_reference_path(cand, acc, EVENT_WEIGHT_DEFAULT)
    blended_shift = mean_path_shift_m(acc, _pts([(p.x, p.y, p.z) for p in blended.points]))
    assert raw_shift == pytest.approx(10.0, abs=1e-6)
    assert blended_shift == pytest.approx(10.0 * EVENT_WEIGHT_DEFAULT, abs=1e-6)


# ----------------------------------------------------------------- the gate

def test_gate_more_corners_improves():
    accepted = _mk_align(model_corners_found=15)
    candidate = _mk_align(model_corners_found=16)
    v = compare_models(accepted, candidate)
    assert v.improves is True
    assert v.regression_reasons == []
    assert any("more corners" in r for r in v.improvement_reasons)


def test_gate_lap_length_closer_improves():
    accepted = _mk_align(lap_length_delta_pct=2.68)
    candidate = _mk_align(lap_length_delta_pct=1.10)
    v = compare_models(accepted, candidate)
    assert v.improves is True
    assert any("lap length closer" in r for r in v.improvement_reasons)


def test_gate_no_change_does_not_improve():
    accepted = _mk_align()
    candidate = _mk_align()
    v = compare_models(accepted, candidate)
    assert v.improves is False
    assert v.improvement_reasons == []
    assert v.regression_reasons == []


def test_gate_fewer_corners_is_regression_even_with_improvement():
    # Candidate has closer lap length (improvement) BUT drops a corner (regression).
    accepted = _mk_align(model_corners_found=16, lap_length_delta_pct=2.68)
    candidate = _mk_align(model_corners_found=15, lap_length_delta_pct=1.0)
    v = compare_models(accepted, candidate)
    assert v.improves is False
    assert any("fewer corners" in r for r in v.regression_reasons)


def test_gate_weaker_match_status_is_regression():
    accepted = _mk_align(match_status=TrackModelMatchStatus.GOOD_MATCH)
    candidate = _mk_align(match_status=TrackModelMatchStatus.PARTIAL_MATCH,
                          lap_length_delta_pct=0.5)
    v = compare_models(accepted, candidate)
    assert v.improves is False
    assert any("weaker match" in r for r in v.regression_reasons)


def test_gate_lower_confidence_is_regression():
    accepted = _mk_align(confidence=1.0)
    candidate = _mk_align(confidence=0.8, lap_length_delta_pct=0.5)
    v = compare_models(accepted, candidate)
    assert v.improves is False
    assert any("lower confidence" in r for r in v.regression_reasons)


# ----------------------------------------------------- candidate round-trip

def test_candidate_export_import_roundtrip(tmp_path):
    align = _mk_align(model_corners_found=16, accepted=False, accepted_at="")
    extras = {"base_accepted_at": "T1", "contributing_laps": 3,
              "contributing_cars": ["Porsche RSR"], "improves": True}
    path = export_candidate_model_json(align, LOC, LAY, extras, output_dir=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "candidate_track_model_v1"
    assert data["contributing_laps"] == 3
    assert data["base_accepted_at"] == "T1"
    # Reconstruct the alignment for promotion.
    reloaded = import_candidate_alignment(path)
    assert reloaded is not None
    assert reloaded.model_corners_found == 16
    assert reloaded.accepted is False


def test_ledger_appends_lines(tmp_path):
    append_refinement_ledger(LOC, LAY, {"decision": "candidate_built", "usable_laps": 2}, models_dir=tmp_path)
    append_refinement_ledger(LOC, LAY, {"decision": "promoted"}, models_dir=tmp_path)
    ledger = tmp_path / refinement_ledger_filename(LOC, LAY)
    lines = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert lines[0]["decision"] == "candidate_built"
    assert lines[1]["decision"] == "promoted"
    assert "ts" in lines[0]  # timestamp auto-stamped


# ------------------------------------------------- orchestration + promotion

def test_refine_no_accepted_model_is_noop(tmp_path):
    from data.track_calibration import CalibrationSession
    session = CalibrationSession(session_id="s", track_location_id=LOC, layout_id=LAY)
    result = refine_from_session(session, LOC, LAY, models_dir=tmp_path)
    assert result.success is False
    assert "no accepted model" in result.reason
    assert result.promotable is False


def _write_accepted(tmp_path, **over):
    align = _mk_align(**over)
    return export_accepted_model_json(align, LOC, LAY, output_dir=tmp_path), align


def test_refine_runs_real_build_pipeline_and_logs_no_candidate(tmp_path):
    # Accepted model exists, but the captured session has no usable laps → the
    # real build_reference_path pipeline runs, yields no candidate, and the round
    # is logged honestly (S4).
    from data.track_calibration import CalibrationSession
    _write_accepted(tmp_path, accepted_at="T1")
    session = CalibrationSession(session_id="s", track_location_id=LOC, layout_id=LAY)
    result = refine_from_session(session, LOC, LAY, contributing_cars=["Porsche RSR"],
                                 models_dir=tmp_path)
    assert result.success is False
    assert result.promotable is False
    assert find_candidate_model_path(LOC, LAY, base_dir=tmp_path) is None  # no candidate written
    ledger = (tmp_path / refinement_ledger_filename(LOC, LAY)).read_text(encoding="utf-8")
    assert "no_candidate" in ledger


def test_promote_replaces_accepted_and_clears_candidate(tmp_path):
    # Accepted with 15 corners; candidate improves to 16, built from this base.
    acc_path, acc = _write_accepted(tmp_path, model_corners_found=15,
                                    accepted_at="2026-07-12T09:00:00+00:00")
    cand = _mk_align(model_corners_found=16, accepted=False, accepted_at="")
    export_candidate_model_json(cand, LOC, LAY,
                                {"base_accepted_at": "2026-07-12T09:00:00+00:00"},
                                output_dir=tmp_path)
    out = promote_candidate(LOC, LAY, models_dir=tmp_path)
    assert out is not None
    # Accepted model now has 16 corners and is accepted.
    promoted = import_accepted_model_json(out)
    assert promoted.model_corners_found == 16
    assert promoted.accepted is True
    assert promoted.accepted_at  # freshly stamped
    # Candidate file removed.
    assert find_candidate_model_path(LOC, LAY, base_dir=tmp_path) is None


def test_promote_refused_when_no_improvement(tmp_path):
    _write_accepted(tmp_path, model_corners_found=16, accepted_at="T1")
    cand = _mk_align(model_corners_found=16, accepted=False)  # identical → no improvement
    export_candidate_model_json(cand, LOC, LAY, {"base_accepted_at": "T1"}, output_dir=tmp_path)
    out = promote_candidate(LOC, LAY, models_dir=tmp_path)
    assert out is None
    # Candidate NOT cleared (still visible), accepted unchanged.
    assert find_candidate_model_path(LOC, LAY, base_dir=tmp_path) is not None
    assert import_accepted_model_json(find_accepted_model_path(LOC, LAY, base_dir=tmp_path)).model_corners_found == 16


def test_promote_refused_on_stale_base(tmp_path):
    # Accepted was re-accepted at T2, but candidate was built from T1 → stale.
    _write_accepted(tmp_path, model_corners_found=15, accepted_at="T2")
    cand = _mk_align(model_corners_found=16, accepted=False)
    export_candidate_model_json(cand, LOC, LAY, {"base_accepted_at": "T1"}, output_dir=tmp_path)
    out = promote_candidate(LOC, LAY, models_dir=tmp_path)
    assert out is None
    ledger = (tmp_path / refinement_ledger_filename(LOC, LAY)).read_text(encoding="utf-8")
    assert "promote_rejected_stale_base" in ledger


def test_discard_candidate(tmp_path):
    cand = _mk_align(accepted=False)
    export_candidate_model_json(cand, LOC, LAY, {}, output_dir=tmp_path)
    assert discard_candidate(LOC, LAY, models_dir=tmp_path) is True
    assert find_candidate_model_path(LOC, LAY, base_dir=tmp_path) is None
    assert discard_candidate(LOC, LAY, models_dir=tmp_path) is False  # already gone
