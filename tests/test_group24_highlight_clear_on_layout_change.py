"""Tests for Group 24 AC1 — clear highlight bounds on layout change."""
import pytest


class FakeDashboard:
    """Minimal stub replicating _tm_on_layout_changed highlight-clear behaviour."""

    def __init__(self):
        self._tm_highlight_start_p = None
        self._tm_highlight_end_p = None
        self._pit_lane_active = False
        self._tm_seed_result = object()  # non-None so method proceeds
        self._config = {}
        self._layout_changed_extra_calls = []

    def _tm_on_layout_changed(self):
        # Group 24 AC1: clear stale highlight bounds from previous track
        self._tm_highlight_start_p = None
        self._tm_highlight_end_p = None
        # Group 24 AC2: reset pit-lane guard on layout change
        self._pit_lane_active = False
        if self._tm_seed_result is None:
            return
        # (remaining method body omitted — only the guard matters for these tests)


def test_highlight_bounds_cleared_after_layout_change():
    """After _tm_on_layout_changed(), both highlight bounds are None."""
    dash = FakeDashboard()
    dash._tm_highlight_start_p = 0.2
    dash._tm_highlight_end_p = 0.6

    dash._tm_on_layout_changed()

    assert dash._tm_highlight_start_p is None
    assert dash._tm_highlight_end_p is None


def test_highlight_bounds_cleared_when_already_none():
    """Method works cleanly when bounds were already None."""
    dash = FakeDashboard()
    dash._tm_highlight_start_p = None
    dash._tm_highlight_end_p = None

    dash._tm_on_layout_changed()

    assert dash._tm_highlight_start_p is None
    assert dash._tm_highlight_end_p is None


def test_highlight_cleared_even_when_seed_result_none():
    """Highlight clear happens before early-return on _tm_seed_result is None."""
    dash = FakeDashboard()
    dash._tm_seed_result = None
    dash._tm_highlight_start_p = 0.1
    dash._tm_highlight_end_p = 0.9

    dash._tm_on_layout_changed()

    assert dash._tm_highlight_start_p is None
    assert dash._tm_highlight_end_p is None


# ---------------------------------------------------------------------------
# AC1 — highlight restored after table refresh (Group 24 addition)
# ---------------------------------------------------------------------------

class FakeDashboardWithRefresh:
    """Stub replicating _tm_refresh_seg_table highlight-restore behaviour."""

    def __init__(self):
        self._tm_highlight_start_p = None
        self._tm_highlight_end_p = None
        self._set_map_highlight_calls = []

    def _tm_set_map_highlight(self, start_p, end_p):
        self._set_map_highlight_calls.append((start_p, end_p))

    def _tm_refresh_seg_table(self):
        """Mirrors the restore-highlight block from dashboard._tm_refresh_seg_table."""
        # (table population omitted — only the highlight restore matters)
        if self._tm_highlight_start_p is not None:
            self._tm_set_map_highlight(self._tm_highlight_start_p, self._tm_highlight_end_p)


def test_highlight_restored_after_table_refresh():
    """After _tm_refresh_seg_table(), _tm_set_map_highlight is called with stored bounds."""
    dash = FakeDashboardWithRefresh()
    dash._tm_highlight_start_p = 0.3
    dash._tm_highlight_end_p = 0.7

    dash._tm_refresh_seg_table()

    assert len(dash._set_map_highlight_calls) == 1
    assert dash._set_map_highlight_calls[0] == (0.3, 0.7)


def test_highlight_not_restored_when_bounds_are_none():
    """When highlight bounds are None, _tm_set_map_highlight is NOT called on refresh."""
    dash = FakeDashboardWithRefresh()
    dash._tm_highlight_start_p = None
    dash._tm_highlight_end_p = None

    dash._tm_refresh_seg_table()

    assert len(dash._set_map_highlight_calls) == 0
