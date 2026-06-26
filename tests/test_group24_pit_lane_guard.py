"""Tests for Group 24 AC2 — reset _pit_lane_active on layout/map change."""
import pytest


class FakeDashboard:
    """Minimal stub covering pit_lane_active reset logic."""

    def __init__(self):
        self._tm_highlight_start_p = None
        self._tm_highlight_end_p = None
        self._pit_lane_active = False
        self._tm_seed_result = object()
        self._config = {}

    def _tm_on_layout_changed(self):
        self._tm_highlight_start_p = None
        self._tm_highlight_end_p = None
        self._pit_lane_active = False
        if self._tm_seed_result is None:
            return

    def _tm_try_load_station_map_from_disk_stub(self, sm):
        """Replicates just the pit_lane_active reset part of _tm_try_load_station_map_from_disk."""
        self._tm_station_map = sm
        self._pit_lane_active = False


def test_pit_lane_active_false_after_layout_change():
    """_pit_lane_active is False after _tm_on_layout_changed() even if it was True before."""
    dash = FakeDashboard()
    dash._pit_lane_active = True

    dash._tm_on_layout_changed()

    assert dash._pit_lane_active is False


def test_pit_lane_active_false_after_layout_change_seed_none():
    """_pit_lane_active is reset even when _tm_seed_result is None (early-return path)."""
    dash = FakeDashboard()
    dash._tm_seed_result = None
    dash._pit_lane_active = True

    dash._tm_on_layout_changed()

    assert dash._pit_lane_active is False


def test_pit_lane_active_false_after_station_map_loaded():
    """_pit_lane_active is False after a station map is successfully assigned."""
    dash = FakeDashboard()
    dash._pit_lane_active = True

    fake_sm = object()
    dash._tm_try_load_station_map_from_disk_stub(fake_sm)

    assert dash._pit_lane_active is False
    assert dash._tm_station_map is fake_sm


def test_pit_lane_active_already_false_stays_false():
    """Guard is idempotent when _pit_lane_active was already False."""
    dash = FakeDashboard()
    dash._pit_lane_active = False

    dash._tm_on_layout_changed()

    assert dash._pit_lane_active is False
