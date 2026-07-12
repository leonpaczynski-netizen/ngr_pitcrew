"""Tests for data/track_refinement.py (continuous refinement, Phase 1).

Covers the safety-critical parts: the non-regression/improvement gate,
candidate persistence round-trip, the ledger, and gated promotion (never
promote a worse candidate; reject a stale base).
"""
from __future__ import annotations

import json

from data.track_model_alignment import (
    SectorAlignmentResult,
    TrackModelAlignmentResult,
    TrackModelMatchStatus,
    export_accepted_model_json,
    find_accepted_model_path,
    import_accepted_model_json,
)
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
