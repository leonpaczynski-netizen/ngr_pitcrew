"""Phase 4: track model and pit lane — D1, D4, D5, D6, D7, D8, D9.

UAT symptom 4: "during track modelling it told you to box, then after you came out it
still asked you to drive the pit lane". The register calls D1 the primary cause.

D2 and D3 were fixed in Phase 0 (the off-by-N baseline, and loading the station map from
disk so mapping is possible for an already-approved track).
"""
from __future__ import annotations

import inspect
import json
import math

import pytest

from data.pit_lane_detection import (
    DIVERGENCE_THRESHOLD_M, detect_pit_lane_traversal, is_pit_lap,
)


# ---------------------------------------------------------------------------
# Geometry helpers — a circular track with a known reference line
# ---------------------------------------------------------------------------
_R = 300.0
_LAP_M = 2 * math.pi * _R


class _S:
    def __init__(self, x, z, t=0):
        self.x, self.z, self.timestamp_ms = x, z, t


class _St:
    def __init__(self, m, x, z):
        self.station_m, self.x, self.z = m, x, z


def _stations():
    return [_St(m, _R * math.cos(m / _LAP_M * 2 * math.pi),
               _R * math.sin(m / _LAP_M * 2 * math.pi))
            for m in range(0, int(_LAP_M), 2)]


def _lap(offset_from=None, offset_to=None, offset_m=0.0, n=5400):
    out = []
    for i in range(n):
        a = i / n * 2 * math.pi
        m = a / (2 * math.pi) * _LAP_M
        r = _R
        if offset_from is not None and offset_from <= m <= offset_to:
            r = _R - offset_m
        out.append(_S(r * math.cos(a), r * math.sin(a), int(i * 1000 / 60)))
    return out


# ---------------------------------------------------------------------------
# D5 — the old detector classified every clean lap as a pit lap
# ---------------------------------------------------------------------------
def test_the_old_detector_flags_a_perfectly_clean_lap():
    """It measures each sample's distance from the LAP'S OWN CENTROID. On any real
    circuit the centroid is the middle of the track, so essentially every sample is
    more than 60m from it. This was only harmless because pit_detection_enabled
    defaults False — turning that flag on without fixing the geometry would have marked
    EVERY lap a pit lap and convergence would have excluded all of them."""
    from data.track_calibration import detect_pit_lap_raw
    assert detect_pit_lap_raw(_lap()) is True


def test_the_old_detector_is_marked_superseded():
    from data.track_calibration import detect_pit_lap_raw
    doc = inspect.getdoc(detect_pit_lap_raw) or ""
    assert "SUPERSEDED" in doc
    assert "centroid" in doc.lower()


def test_the_new_detector_leaves_a_clean_lap_alone():
    assert is_pit_lap(_lap(), _stations()) is False


# ---------------------------------------------------------------------------
# D6 — a threshold that matches a pit lane, not a distance constant
# ---------------------------------------------------------------------------
def test_a_real_pit_lane_offset_is_detected():
    """Real pit lanes run 15-30m from the racing line; the old 60m threshold meant a
    correct traversal read as "I couldn't see the pit lane on that lap"."""
    t = detect_pit_lane_traversal(_lap(400, 640, 25.0), _stations())
    assert t.detected is True
    assert 20 <= t.max_offset_m <= 30
    assert t.length_m >= 200


def test_the_threshold_is_tighter_than_the_old_constant():
    from data.track_station_map import _PIT_LANE_THRESHOLD_M
    assert DIVERGENCE_THRESHOLD_M < _PIT_LANE_THRESHOLD_M
    assert 10 <= DIVERGENCE_THRESHOLD_M <= 15


def test_a_wide_line_is_not_a_pit_lane():
    """The threshold has to separate a pit lane from a driver running wide."""
    assert is_pit_lap(_lap(400, 460, 8.0), _stations()) is False


def test_a_short_excursion_is_not_a_pit_lane():
    """A pit lane is a road, not a mistake."""
    assert is_pit_lap(_lap(400, 440, 25.0), _stations()) is False


def test_leaving_the_line_without_rejoining_is_not_a_pit_lane():
    """A car that leaves and never returns went off and stopped."""
    samples = _lap()[:2700] + [_S(_R + 200, 0.0, 0)] * 600
    assert is_pit_lap(samples, _stations()) is False


def test_the_traversal_reports_where_it_happened():
    t = detect_pit_lane_traversal(_lap(400, 640, 25.0), _stations())
    assert 380 <= t.entry_station_m <= 420
    assert "rejoined" in t.reason


def test_detection_needs_a_reference_line():
    """Without a measured line there is nothing to diverge FROM — guessing at that is
    what produced the centroid version."""
    t = detect_pit_lane_traversal(_lap(400, 640, 25.0), [])
    assert t.detected is False
    assert "station map" in t.reason


def test_detection_never_raises_on_junk():
    for samples, stations in (([], []), ([object()], _stations()),
                              (_lap(), [object()]), (None, None)):
        assert detect_pit_lane_traversal(samples, stations) is not None


def test_stride_reduces_the_work_without_losing_a_real_traversal():
    """The full search is O(samples x stations) — a 90s lap at 60Hz against a 5km
    centreline is ~27 million distance computations (defect D9)."""
    assert detect_pit_lane_traversal(_lap(400, 640, 25.0), _stations(), stride=4).detected


# ---------------------------------------------------------------------------
# D1 / D8 — boxing is detected, not clicked
# ---------------------------------------------------------------------------
def _bridge(speed, converged=True, pit_mode=False, ticks=0):
    from ui.live_shell_bridge import LiveShellBridge
    packet = type("P", (), {"speed_kmh": speed})()
    window = type("W", (), {"_last_packet": packet})()
    stub = type("S", (), {
        "_window": window, "_tm_converged": converged, "_pit_lane_mode": pit_mode,
        "_box_ticks": ticks, "_BOX_SPEED_KMH": LiveShellBridge._BOX_SPEED_KMH,
        "_BOX_TICKS": LiveShellBridge._BOX_TICKS})()
    stub._detect_box = LiveShellBridge._detect_box.__get__(stub)
    return stub


def test_sustained_pit_speed_reads_as_boxing():
    """"Box this lap" meant PRESS THE STOP RECORDING BUTTON. stop_capture had exactly
    one caller — a widget click — and in VR the driver cannot reach it, so the physical
    pit stop was a no-op and the same callout fired again next lap."""
    from ui.live_shell_bridge import LiveShellBridge
    b = _bridge(45.0)
    fired = [b._detect_box() for _ in range(LiveShellBridge._BOX_TICKS)]
    assert fired[-1] is True
    assert fired[0] is False, "one slow tick is a corner, not a pit lane"


def test_a_slow_corner_does_not_read_as_boxing():
    b = _bridge(45.0)
    b._detect_box()
    b._window._last_packet.speed_kmh = 140.0
    assert b._detect_box() is False
    assert b._box_ticks == 0


def test_being_stationary_is_not_boxing():
    """In the garage or menus the car is stopped; that is not a pit entry."""
    b = _bridge(0.0)
    for _ in range(10):
        assert b._detect_box() is False


def test_no_telemetry_is_not_boxing():
    from ui.live_shell_bridge import LiveShellBridge
    stub = type("S", (), {"_window": type("W", (), {})(), "_box_ticks": 0,
                          "_BOX_SPEED_KMH": 65.0, "_BOX_TICKS": 5})()
    assert LiveShellBridge._detect_box(stub) is False


def test_boxing_only_finishes_the_model_once_it_has_converged():
    """Slowing down mid-capture for any other reason must not end the session early."""
    from ui.live_shell_bridge import LiveShellBridge
    calls = []
    b = _bridge(45.0, converged=False, ticks=99)
    b._on_track_action = lambda a: calls.append(a)
    b._track_status = lambda t: None
    LiveShellBridge._auto_box_if_converged(b)
    assert calls == []


def test_boxing_when_converged_finishes_the_model():
    from ui.live_shell_bridge import LiveShellBridge
    calls = []
    b = _bridge(45.0, converged=True, ticks=99)
    b._on_track_action = lambda a: calls.append(a)
    b._track_status = lambda t: None
    LiveShellBridge._auto_box_if_converged(b)
    assert calls == ["stop_capture"]


def test_boxing_does_nothing_once_the_lane_is_being_mapped():
    from ui.live_shell_bridge import LiveShellBridge
    calls = []
    b = _bridge(45.0, converged=True, pit_mode=True, ticks=99)
    b._on_track_action = lambda a: calls.append(a)
    b._track_status = lambda t: None
    LiveShellBridge._auto_box_if_converged(b)
    assert calls == []


def test_the_instruction_no_longer_tells_the_driver_to_press_something():
    """D8 — the app said "a drive-through is enough, you don't need to stop" while the
    only detector needed a 3-second stop in RACING phase, which Time Trial never
    reaches. Instruction and detector now describe the same act."""
    from data.track_convergence import ConvergenceResult, convergence_coach_message
    msg = convergence_coach_message(
        ConvergenceResult(converged=True, usable_laps=5, spread_pct=0.5, reason=""))
    assert "nothing to press" in msg.lower()
    assert "no need to stop" in msg.lower()


# ---------------------------------------------------------------------------
# D4 — the pit lane is a step, with on-disk readiness
# ---------------------------------------------------------------------------
def test_the_rail_has_a_pit_lane_step():
    """The six-step rail had no pit action, state or message; the outstanding step
    lived only in _pit_lane_mode, an in-memory flag lost on restart."""
    from data.track_modelling_coordinator import (
        TrackModellingAction, TrackModellingState, WorkflowStep,
    )
    assert WorkflowStep.MAP_PIT_LANE
    assert TrackModellingState.PIT_LANE_PENDING
    assert TrackModellingAction.MAP_PIT_LANE and TrackModellingAction.PIT_LANE_MAPPED


def test_the_pit_lane_state_has_a_next_step_message():
    from data.track_modelling_coordinator import _NEXT_STEP, TrackModellingState
    msg = _NEXT_STEP[TrackModellingState.PIT_LANE_PENDING]
    assert "pit lane" in msg.lower()
    assert "nothing to press" in msg.lower()


def test_an_accepted_model_can_be_sent_back_to_map_its_lane():
    """Confirmed on the driver's disk: the Monza model carries "accepted": true beside
    "pit_lane": null — an approved-but-unmapped track read as finished."""
    from data.track_modelling_coordinator import (
        _TRANSITIONS, TrackModellingAction, TrackModellingState,
    )
    assert (_TRANSITIONS[TrackModellingState.ACTIVE][TrackModellingAction.MAP_PIT_LANE]
            is TrackModellingState.PIT_LANE_PENDING)
    assert (_TRANSITIONS[TrackModellingState.PIT_LANE_PENDING]
            [TrackModellingAction.PIT_LANE_MAPPED] is TrackModellingState.ACTIVE)


def test_disk_readiness_reports_the_pit_lane():
    from data.track_readiness_disk import audit_track_assets_on_disk
    ctx = audit_track_assets_on_disk("nowhere", "nolayout")
    assert hasattr(ctx.availability, "pit_lane_available")
    assert ctx.availability.pit_lane_available is False


# ---------------------------------------------------------------------------
# D7 — the mapping must reach the store the live engineer reads
# ---------------------------------------------------------------------------
def test_the_mapper_publishes_to_the_track_library(tmp_path, monkeypatch):
    """Modelling wrote station_map.pit_lane; the live resolver reads
    data/track_library, whose index.json is an empty tracks list. Live pit
    corroboration was permanently inert however many times the lane was mapped."""
    import data.track_library as lib
    from services.track_modelling import TrackModellingService

    monkeypatch.setattr(lib, "TRACK_LIBRARY_BASE", tmp_path)
    svc = TrackModellingService.__new__(TrackModellingService)
    svc._session = type("Sess", (), {"location_id": "monza", "layout_id": "gp"})()
    boundary = type("B", (), {"segments": [{"start_m": 100.0, "end_m": 420.0}]})()
    assert svc._publish_pit_lane_to_library(boundary) is True

    written = tmp_path / "tracks" / "monza" / "layouts" / "gp" / "pit_lane.json"
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["available"] is True
    assert payload["segments"] == [{"start_m": 100.0, "end_m": 420.0}]
    assert "measured" in payload["source"]


def test_publishing_a_lane_with_no_segments_is_refused(tmp_path, monkeypatch):
    import data.track_library as lib
    from services.track_modelling import TrackModellingService

    monkeypatch.setattr(lib, "TRACK_LIBRARY_BASE", tmp_path)
    svc = TrackModellingService.__new__(TrackModellingService)
    svc._session = type("Sess", (), {"location_id": "monza", "layout_id": "gp"})()
    assert svc._publish_pit_lane_to_library(type("B", (), {"segments": []})()) is False


def test_publishing_never_raises(tmp_path, monkeypatch):
    from services.track_modelling import TrackModellingService
    svc = TrackModellingService.__new__(TrackModellingService)
    svc._session = type("Sess", (), {"location_id": "", "layout_id": ""})()
    assert svc._publish_pit_lane_to_library(None) is False


# ---------------------------------------------------------------------------
# D9 — off the Qt thread
# ---------------------------------------------------------------------------
def test_pit_mapping_runs_off_the_qt_thread():
    """~27 million distance computations ran synchronously inside a 750ms timer,
    wrapped in a bare except: a slow attempt froze the UI and a failing one was
    indistinguishable from a no-op."""
    from ui.live_shell_bridge import LiveShellBridge
    src = inspect.getsource(LiveShellBridge._try_map_pit_lane)
    assert "_spawn" in src
    assert "_pit_map_done" in src


def test_only_one_mapping_attempt_runs_at_a_time():
    from ui.live_shell_bridge import LiveShellBridge
    src = inspect.getsource(LiveShellBridge._try_map_pit_lane)
    assert "_pit_map_pending" in src


def test_the_result_is_applied_on_the_qt_thread():
    from ui.live_shell_bridge import LiveShellBridge
    assert hasattr(LiveShellBridge, "_on_pit_map_done")
    assert hasattr(LiveShellBridge, "_pit_map_done")
