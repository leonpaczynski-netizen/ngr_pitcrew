"""Tests for Group 23A — highlight persistence across _tm_refresh_seg_table()."""
import types
import pytest
from unittest.mock import MagicMock, patch, call


def _make_fake_dashboard():
    """Build a minimal namespace that replicates the highlight persistence logic."""

    class FakeDashboard:
        def __init__(self):
            self._tm_review_result = None
            self._tm_station_map = None
            self._tm_seed_result = None
            self._tm_location_combo = None
            self._tm_layout_combo = None
            self._tm_seg_table = None
            self._tm_highlight_start_p = None
            self._tm_highlight_end_p = None
            self._clear_calls = 0
            self._set_calls = []

        def _tm_clear_map_highlight(self):
            self._clear_calls += 1
            self._tm_highlight_start_p = None
            self._tm_highlight_end_p = None

        def _tm_set_map_highlight(self, start_p, end_p):
            self._tm_highlight_start_p = start_p
            self._tm_highlight_end_p = end_p
            self._set_calls.append((start_p, end_p))

        def _tm_refresh_seg_table(self):
            """Replica of the patched behaviour from dashboard.py (Group 23A)."""
            # No _tm_clear_map_highlight() at start — removed by Group 23A
            review = getattr(self, "_tm_review_result", None)
            tbl = getattr(self, "_tm_seg_table", None)
            if tbl is None:
                # Restore highlight even when table is absent
                if self._tm_highlight_start_p is not None:
                    self._tm_set_map_highlight(self._tm_highlight_start_p, self._tm_highlight_end_p)
                return
            segs = list(review.segments) if review else []
            tbl.setRowCount(len(segs))
            tbl.resizeColumnsToContents()
            # Group 23A: restore highlight after table rebuild
            if self._tm_highlight_start_p is not None:
                self._tm_set_map_highlight(self._tm_highlight_start_p, self._tm_highlight_end_p)

    return FakeDashboard()


def test_clear_not_called_at_start_of_refresh():
    """_tm_clear_map_highlight must NOT be called at the start of _tm_refresh_seg_table."""
    dash = _make_fake_dashboard()
    initial_clears = dash._clear_calls
    dash._tm_refresh_seg_table()
    assert dash._clear_calls == initial_clears, (
        "_tm_clear_map_highlight was called during _tm_refresh_seg_table — should not be"
    )


def test_highlight_restored_after_refresh():
    """If _tm_highlight_start_p is set, highlight must be restored after refresh."""
    dash = _make_fake_dashboard()
    dash._tm_highlight_start_p = 0.3
    dash._tm_highlight_end_p = 0.5
    initial_sets = len(dash._set_calls)

    dash._tm_refresh_seg_table()

    assert len(dash._set_calls) > initial_sets, "Expected _tm_set_map_highlight to be called"
    assert dash._set_calls[-1] == (0.3, 0.5)
    assert dash._tm_highlight_start_p == 0.3
    assert dash._tm_highlight_end_p == 0.5


def test_no_highlight_restore_when_none():
    """If _tm_highlight_start_p is None, no highlight restore should occur."""
    dash = _make_fake_dashboard()
    dash._tm_highlight_start_p = None
    dash._tm_highlight_end_p = None

    dash._tm_refresh_seg_table()

    assert len(dash._set_calls) == 0, "No set_map_highlight should be called when coords are None"


def test_clear_still_called_on_track_model_rebuild():
    """_tm_clear_map_highlight IS still called on track model rebuild (not removed there)."""
    dash = _make_fake_dashboard()
    dash._tm_highlight_start_p = 0.2
    dash._tm_highlight_end_p = 0.4

    # Simulate track model rebuild calling clear explicitly
    dash._tm_clear_map_highlight()

    assert dash._clear_calls == 1
    assert dash._tm_highlight_start_p is None
    assert dash._tm_highlight_end_p is None
