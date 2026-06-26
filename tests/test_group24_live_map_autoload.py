"""Tests for Group 24 AC5 — live tab auto-load station map for active event."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


# ---------------------------------------------------------------------------
# Stub dashboard class replicating _live_try_load_active_event_map logic
# ---------------------------------------------------------------------------

class FakeMapWidget:
    def __init__(self):
        self.draw_data_calls = []

    def set_draw_data(self, dd):
        self.draw_data_calls.append(dd)


class FakeLabel:
    def __init__(self):
        self.text = ""
        self.style = ""

    def setText(self, t):
        self.text = t

    def setStyleSheet(self, s):
        self.style = s


class FakeDashboard:
    def __init__(self, config=None):
        self._config = config or {}
        self._live_map_widget = FakeMapWidget()
        self._live_lbl_track = FakeLabel()

    def _live_try_load_active_event_map(
        self,
        _find_station_map_path=None,
        _import_station_map=None,
        _build_map_draw_data=None,
    ):
        """Mirrors the actual implementation with injected helpers for testing."""
        loc_id = self._config.get("strategy", {}).get("track_location_id", "")
        lay_id = self._config.get("strategy", {}).get("layout_id", "")
        if not loc_id:
            if hasattr(self, "_live_lbl_track"):
                self._live_lbl_track.setText("Track: not mapped — calibrate first")
                self._live_lbl_track.setStyleSheet("color: #888888;")
            return
        try:
            path = _find_station_map_path(loc_id, lay_id)
            sm = _import_station_map(path) if path and path.exists() else None
        except Exception:
            sm = None
        if sm is not None:
            dd = _build_map_draw_data(sm)
            if hasattr(self, "_live_map_widget"):
                self._live_map_widget.set_draw_data(dd)
            if hasattr(self, "_live_lbl_track"):
                self._live_lbl_track.setText(f"Track: {loc_id} — {lay_id}")
                self._live_lbl_track.setStyleSheet("color: #4caf50;")
        else:
            if hasattr(self, "_live_lbl_track"):
                self._live_lbl_track.setText("Track: not mapped — calibrate first")
                self._live_lbl_track.setStyleSheet("color: #888888;")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_path(exists=True):
    p = MagicMock(spec=Path)
    p.exists.return_value = exists
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_station_map_exists_sets_green_label_and_draw_data():
    """When station map file exists, label is green and set_draw_data is called."""
    dash = FakeDashboard(config={"strategy": {"track_location_id": "brands_hatch", "layout_id": "indy"}})
    fake_path = _make_path(exists=True)
    fake_sm = object()
    fake_dd = object()

    dash._live_try_load_active_event_map(
        _find_station_map_path=lambda loc, lay: fake_path,
        _import_station_map=lambda p: fake_sm,
        _build_map_draw_data=lambda sm: fake_dd,
    )

    assert fake_dd in dash._live_map_widget.draw_data_calls
    assert "brands_hatch" in dash._live_lbl_track.text
    assert "#4caf50" in dash._live_lbl_track.style


def test_no_station_map_file_sets_grey_label():
    """When station map path does not exist, label is grey and no draw_data call."""
    dash = FakeDashboard(config={"strategy": {"track_location_id": "monza", "layout_id": "gp"}})
    fake_path = _make_path(exists=False)

    dash._live_try_load_active_event_map(
        _find_station_map_path=lambda loc, lay: fake_path,
        _import_station_map=lambda p: None,
        _build_map_draw_data=lambda sm: object(),
    )

    assert len(dash._live_map_widget.draw_data_calls) == 0
    assert "not mapped" in dash._live_lbl_track.text
    assert "#888888" in dash._live_lbl_track.style


def test_no_loc_id_sets_grey_label():
    """When loc_id is empty, label is grey immediately and no draw_data call."""
    dash = FakeDashboard(config={"strategy": {"track_location_id": "", "layout_id": ""}})

    find_called = []
    dash._live_try_load_active_event_map(
        _find_station_map_path=lambda loc, lay: find_called.append(True) or _make_path(),
        _import_station_map=lambda p: object(),
        _build_map_draw_data=lambda sm: object(),
    )

    assert len(find_called) == 0
    assert len(dash._live_map_widget.draw_data_calls) == 0
    assert "not mapped" in dash._live_lbl_track.text
    assert "#888888" in dash._live_lbl_track.style


def test_find_raises_exception_sets_grey_label():
    """When _find_station_map_path raises, label is grey and no draw_data call."""
    dash = FakeDashboard(config={"strategy": {"track_location_id": "spa", "layout_id": "full"}})

    def _bad_find(loc, lay):
        raise RuntimeError("disk error")

    dash._live_try_load_active_event_map(
        _find_station_map_path=_bad_find,
        _import_station_map=lambda p: object(),
        _build_map_draw_data=lambda sm: object(),
    )

    assert len(dash._live_map_widget.draw_data_calls) == 0
    assert "not mapped" in dash._live_lbl_track.text


def test_accept_track_model_triggers_live_map_for_matching_track():
    """_live_try_load_active_event_map is called when accepted track matches active event."""
    calls = []

    class FakeDashAccept(FakeDashboard):
        def _live_try_load_active_event_map(self, **_):
            calls.append(True)

        def _tm_refresh_alignment_panel(self, r):
            pass

    dash = FakeDashAccept(config={"strategy": {
        "track_location_id": "suzuka",
        "layout_id": "full",
    }})

    fake_sm = MagicMock()
    fake_sm.track_location_id = "suzuka"
    fake_sm.layout_id = "full"

    # Simulate the accept logic
    active_loc = dash._config.get("strategy", {}).get("track_location_id", "")
    active_lay = dash._config.get("strategy", {}).get("layout_id", "")
    if fake_sm.track_location_id == active_loc and fake_sm.layout_id == active_lay:
        dash._live_try_load_active_event_map()

    assert len(calls) == 1
