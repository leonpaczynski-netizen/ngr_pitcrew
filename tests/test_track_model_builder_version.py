"""Builder-version stamping + stale-model flagging (Stage 5, migration safety).

The accuracy overhaul is a rebuild IN PLACE, so models already on disk were built by the
previous engine. Every model the new engine writes is stamped with its builder_version;
a model stamped with an older version (or none) must be flagged for re-modelling, never
silently trusted.
"""

from __future__ import annotations

import json

import pytest

from data.track_geometry_core import (
    TRACK_MODEL_BUILDER_VERSION, builder_version_is_current,
)
from ui.track_modelling_vm import format_model_trust_badge


# --------------------------------------------------------------------------- helper
def test_current_version_is_current():
    assert builder_version_is_current(TRACK_MODEL_BUILDER_VERSION) is True


def test_missing_or_older_version_is_not_current():
    assert builder_version_is_current(None) is False
    assert builder_version_is_current("") is False
    assert builder_version_is_current("1.0") is False
    assert builder_version_is_current("  ") is False


# --------------------------------------------------------------------------- stamping
def test_accepted_model_export_stamps_builder_version(tmp_path):
    from data.track_model_alignment import (
        export_accepted_model_json, TrackModelAlignmentResult, TrackModelMatchStatus,
        SectorAlignmentResult,
    )
    result = TrackModelAlignmentResult(
        match_status=TrackModelMatchStatus.ACCEPTABLE_MATCH,
        seed_corners_expected=12, model_corners_found=12, extra_peaks_suppressed=0,
        placeholder_count=0, lap_length_m_model=5800.0, lap_length_m_seed=5800.0,
        lap_length_delta_pct=0.0, station_count=5800, confidence=0.9,
        corner_alignments=[], sector_alignment=SectorAlignmentResult(0, "not_available", "x"),
        blockers=[], warnings=[], accepted=True)
    path = export_accepted_model_json(result, "loc", "loc__lay", output_dir=tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["builder_version"] == TRACK_MODEL_BUILDER_VERSION


def test_reviewed_segments_export_stamps_builder_version(tmp_path):
    from data.track_segment_review import (
        TrackModelReviewResult, export_review_json,
    )
    from data.track_segment_detection import TrackSegmentDetectionConfidence
    review = TrackModelReviewResult(
        track_location_id="loc", layout_id="loc__lay", calibration_car_id="car",
        source_lap_count=3, detected_corner_count=0, expected_corner_count=0,
        detection_confidence=TrackSegmentDetectionConfidence.MEDIUM, segments=[])
    path = export_review_json(review, output_dir=tmp_path, session_id="sid")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["builder_version"] == TRACK_MODEL_BUILDER_VERSION


# --------------------------------------------------------------------------- badge
def test_stale_builder_reads_remodel_regardless_of_source():
    # Even a would-be "AI-ready / verified" model reads RE-MODEL when built by an old engine.
    text, tone = format_model_trust_badge(
        {"source_type": "Reviewed — AI-ready", "ai_ready": "Yes", "builder_stale": True})
    assert tone == "warn"
    assert "RE-MODEL" in text.upper()


def test_current_builder_does_not_trigger_remodel():
    text, tone = format_model_trust_badge(
        {"source_type": "Reviewed — AI-ready", "ai_ready": "Yes", "builder_stale": False})
    assert "RE-MODEL" not in text.upper()
    assert tone == "success"


# --------------------------------------------------------------------------- live wiring
def _review(builder_version):
    from data.track_segment_review import TrackModelReviewResult
    from data.track_segment_detection import TrackSegmentDetectionConfidence
    return TrackModelReviewResult(
        track_location_id="loc", layout_id="loc__lay", calibration_car_id="car",
        source_lap_count=3, detected_corner_count=0, expected_corner_count=0,
        detection_confidence=TrackSegmentDetectionConfidence.MEDIUM, segments=[],
        builder_version=builder_version)


def test_review_roundtrip_carries_builder_version(tmp_path):
    from data.track_segment_review import export_review_json, import_review_json
    path = export_review_json(_review(TRACK_MODEL_BUILDER_VERSION),
                              output_dir=tmp_path, session_id="sid")
    loaded = import_review_json(path)
    assert loaded.builder_version == TRACK_MODEL_BUILDER_VERSION


def test_old_file_without_builder_version_loads_blank(tmp_path):
    import json as _json
    from data.track_segment_review import _REVIEW_SCHEMA, import_review_json
    doc = {"schema": _REVIEW_SCHEMA, "track_location_id": "loc", "layout_id": "loc__lay",
           "calibration_car_id": "car", "source_lap_count": 3, "detected_corner_count": 0,
           "expected_corner_count": 0, "detection_confidence": "medium", "segments": []}
    p = tmp_path / "loc__loc__lay__reviewed_segments__old.json"
    p.write_text(_json.dumps(doc), encoding="utf-8")
    loaded = import_review_json(p)
    assert loaded.builder_version == ""            # pre-overhaul file


def test_resolved_model_flags_stale_and_badge_says_remodel():
    from pathlib import Path
    from data.track_model_resolver import _build_resolved_model
    from ui.track_modelling_vm import format_resolver_summary, format_model_trust_badge
    import types
    # An old-engine reviewed model → stale → badge says RE-MODEL.
    old = _build_resolved_model(_review(""), Path("x.json"))
    assert old.builder_stale is True
    result = types.SimpleNamespace(resolution_status="resolved", all_candidate_paths=[],
                                   resolved_model=old)
    summary = format_resolver_summary(result)
    assert summary["builder_stale"] is True
    _text, tone = format_model_trust_badge(summary)
    assert tone == "warn" and "RE-MODEL" in _text.upper()
    # A current-engine model is not stale.
    cur = _build_resolved_model(_review(TRACK_MODEL_BUILDER_VERSION), Path("x.json"))
    assert cur.builder_stale is False
