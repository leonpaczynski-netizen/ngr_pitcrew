"""Headless build → validate → activate pipeline for the guided track-modelling flow.

These verify the SEQUENCE and honesty of ``services/track_modelling_pipeline``: the
right domain calls in the right order, the session flags that gate the coordinator,
and that a sub-threshold validation keeps the work instead of destroying it. The heavy
geometry domain is stubbed — the pipeline owns sequencing, not algorithms.
"""

from __future__ import annotations

import types

import pytest

from data.track_modelling_session import TrackModellingSession
from services.track_modelling import TrackModellingService
from services.track_modelling_pipeline import (
    build_track_model_builders, corners_for_review,
)


# --------------------------------------------------------------------------- fakes
class _RefPath:
    points = [object()]
    track_location_id = "loc"
    layout_id = "loc__lay"


class _BuildResult:
    def __init__(self, success=True, warnings=()):
        self.success = success
        self.reference_path = _RefPath() if success else None
        self.warnings = list(warnings)


class _Ctrl:
    """A capture controller stub covering the methods the pipeline calls."""

    def __init__(self, build_success=True):
        self._session = object()
        self._build = _BuildResult(success=build_success)
        self.saved = False

    def build_reference_path(self):
        return self._build

    def save_reference_path(self, output_dir=None):
        self.saved = True
        return None

    def get_status_summary(self):
        return {"usable_laps": 2, "lap_count": 3}


class _StationMap:
    track_location_id = "loc"
    layout_id = "loc__lay"


class _MatchStatus:
    def __init__(self, name):
        self.name = name


class _Alignment:
    def __init__(self, status="GOOD_MATCH", blockers=()):
        self.match_status = _MatchStatus(status)
        self.blockers = list(blockers)
        self.accepted = False
        self.accepted_at = ""


def _selected_session():
    return TrackModellingSession(location_id="loc", layout_id="loc__lay")


def _svc(controller):
    svc = TrackModellingService(
        capture_controller=controller,
        builders=build_track_model_builders(controller))
    svc.select_track("loc", "loc__lay")
    return svc


def _stub_build_domain(monkeypatch, detection=None, review=None):
    import data.track_station_map as sm_mod
    import data.track_segment_detection as det_mod
    import data.track_segment_review as rev_mod
    import data.track_intelligence as ti_mod
    monkeypatch.setattr(sm_mod, "build_track_station_map",
                        lambda ref, layout_seed=None, **k: _StationMap(), raising=True)
    monkeypatch.setattr(sm_mod, "export_station_map_json",
                        lambda sm, output_dir=None: None, raising=True)
    monkeypatch.setattr(det_mod, "detect_track_segments",
                        lambda *a, **k: (detection if detection is not None
                                         else types.SimpleNamespace(success=True, segments=[])),
                        raising=True)
    monkeypatch.setattr(rev_mod, "create_review_from_detection",
                        lambda d: (review if review is not None
                                   else types.SimpleNamespace(segments=[])),
                        raising=True)
    monkeypatch.setattr(ti_mod, "resolve_track_layout",
                        lambda loc, lay, yaml_path=None: None, raising=True)


# --------------------------------------------------------------------------- build
def test_build_without_a_controller_is_an_error():
    svc = TrackModellingService(builders=build_track_model_builders(None))
    svc.select_track("loc", "loc__lay")
    svc._session = svc.session.with_(has_captured_laps=True)
    result = svc.perform("build_model")
    assert result.ok is False
    assert "controller" in svc.session.error_message.lower()


def test_build_reports_a_failed_reference_path(monkeypatch):
    _stub_build_domain(monkeypatch)
    svc = _svc(_Ctrl(build_success=False))
    svc._session = svc.session.with_(has_captured_laps=True)
    result = svc.perform("build_model")
    assert result.ok is False
    assert "reference path" in svc.session.error_message.lower()


def test_build_happy_path_sets_the_model_flags(monkeypatch):
    _stub_build_domain(monkeypatch)
    ctrl = _Ctrl()
    svc = _svc(ctrl)
    svc._session = svc.session.with_(has_captured_laps=True)
    result = svc.perform("build_model")
    assert result.ok is True
    assert svc.session.has_reference_path is True
    assert svc.session.has_station_map is True
    assert svc.session.has_segments is True
    assert svc.session.artefact("review") is not None
    # The path is NOT persisted at build time — that would auto-approve the model and
    # kill the Validate step. Persistence is deferred to activate.
    assert ctrl.saved is False


# ------------------------------------------------------------------------- corners
def test_corners_for_review_filters_overlays_and_maps_fields():
    from data.track_segment_detection import TrackSegmentType as T
    corner = types.SimpleNamespace(
        segment_type=T.CORNER if hasattr(T, "CORNER") else list(T)[0],
        turn_number=3, display_name="Turn 3",
        confidence=types.SimpleNamespace(value="high"), warnings=["short sample"])
    overlay = types.SimpleNamespace(
        segment_type=T.BRAKING_ZONE, turn_number=None,
        display_name="Braking", confidence=types.SimpleNamespace(value="low"), warnings=[])
    review = types.SimpleNamespace(segments=[corner, overlay])
    session = _selected_session().with_artefact("review", review)
    rows = corners_for_review(session)
    assert len(rows) == 1                    # the braking overlay is filtered out
    assert rows[0]["number"] == 3
    assert rows[0]["name"] == "Turn 3"
    assert rows[0]["confidence"] == "high"
    assert "short sample" in rows[0]["note"]


# ------------------------------------------------------------------------ validate
def test_validate_before_build_is_refused():
    svc = _svc(_Ctrl())
    result = svc.perform("build_model")   # sets up flags via stubbed domain? no — needs laps
    # Without any station map artefact, validate must refuse.
    svc._session = svc.session.with_(has_segments=True)   # make VALIDATE legal in coordinator
    result = svc.perform("validate")
    assert result.ok is False
    assert "build" in svc.session.error_message.lower()


def test_validate_below_threshold_keeps_the_work(monkeypatch):
    import data.track_model_alignment as al_mod
    import data.track_intelligence as ti_mod
    monkeypatch.setattr(ti_mod, "resolve_track_layout",
                        lambda loc, lay, yaml_path=None: None, raising=True)
    monkeypatch.setattr(al_mod, "align_track_model",
                        lambda sm, layout_seed=None: _Alignment("PARTIAL_MATCH"),
                        raising=True)
    svc = _svc(_Ctrl())
    svc._session = svc.session.with_(has_segments=True).with_artefact("station_map", _StationMap())
    result = svc.perform("validate")
    assert result.ok is True                     # NOT an error — the model is kept
    assert svc.session.validation_passed is False
    assert svc.session.error is False
    assert "line up" in result.reason.lower()


def test_validate_good_match_passes(monkeypatch):
    import data.track_model_alignment as al_mod
    import data.track_intelligence as ti_mod
    monkeypatch.setattr(ti_mod, "resolve_track_layout",
                        lambda loc, lay, yaml_path=None: None, raising=True)
    monkeypatch.setattr(al_mod, "align_track_model",
                        lambda sm, layout_seed=None: _Alignment("GOOD_MATCH"),
                        raising=True)
    svc = _svc(_Ctrl())
    svc._session = svc.session.with_(has_segments=True).with_artefact("station_map", _StationMap())
    result = svc.perform("validate")
    assert result.ok is True
    assert svc.session.validation_passed is True


# ------------------------------------------------------------------------ activate
def test_activate_before_validate_is_refused():
    # VALIDATED state (a model exists + validation passed) is what makes ACTIVATE legal;
    # here there is no alignment artefact, so the activate runner itself must refuse.
    svc = _svc(_Ctrl())
    svc._session = svc.session.with_(validation_passed=True, has_station_map=True)
    result = svc.perform("activate")
    assert result.ok is False
    assert "validate" in svc.session.error_message.lower()


def test_activate_writes_the_accepted_model_and_goes_active(monkeypatch):
    import data.track_model_alignment as al_mod
    import data.track_segment_review as rev_mod
    calls = {"accepted": 0, "review": 0}

    def _export_accepted(alignment, loc, lay, output_dir=None):
        calls["accepted"] += 1
        assert alignment.accepted is True         # marked before writing
        return "path"

    monkeypatch.setattr(al_mod, "export_accepted_model_json", _export_accepted, raising=True)
    monkeypatch.setattr(rev_mod, "export_review_json",
                        lambda review, output_dir=None, session_id="":
                        calls.__setitem__("review", calls["review"] + 1) or "p",
                        raising=True)

    svc = _svc(_Ctrl())
    alignment = _Alignment("GOOD_MATCH")
    review = types.SimpleNamespace(segments=[], track_location_id="", layout_id="")
    svc._session = (svc.session
                    .with_(validation_passed=True)
                    .with_artefact("station_map", _StationMap())
                    .with_artefact("alignment", alignment)
                    .with_artefact("review", review))
    ctrl = svc._controller
    result = svc.perform("activate")
    assert result.ok is True
    assert svc.session.model_active is True
    assert calls["accepted"] == 1
    assert calls["review"] == 1
    assert review.track_location_id == "loc"      # stamped with the combo ids
    assert ctrl.saved is True                     # the path is persisted at activate
