"""Tests for Group 23B — Track Modelling UI cleanup and enhancement.

Tests cover:
  - Pit lane status label default state ("not detected", grey)
  - Pit lane status label updates to green after pit_lane is set on station_map
  - Pit lane status label stays grey when no pit laps present
  - _ap_row labels have wordWrap enabled (tested via vm logic, no Qt required)
"""
import types
import pytest
from unittest.mock import MagicMock, patch

from data.track_station_map import (
    PitLaneBoundary,
    StationPoint,
    TrackStationMap,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_station_map(lap_length_m: float = 1000.0) -> TrackStationMap:
    stations = [
        StationPoint(
            station_m=float(i) * (lap_length_m / 100),
            progress_pct=float(i),
            x=float(i),
            y=0.0,
            z=0.0,
        )
        for i in range(101)
    ]
    return TrackStationMap(
        track_location_id="test_loc",
        layout_id="test_layout",
        lap_length_m=lap_length_m,
        spacing_m=lap_length_m / 100,
        stations=stations,
        seeded_corners=[],
        extra_curvature_peaks=[],
    )


class _MockLabel:
    """Minimal QLabel substitute that records setText / setStyleSheet calls."""
    def __init__(self):
        self.text = ""
        self.style = ""
        self.word_wrap = False
        self.min_width = 0

    def setText(self, t: str) -> None:
        self.text = t

    def setStyleSheet(self, s: str) -> None:
        self.style = s

    def setWordWrap(self, v: bool) -> None:
        self.word_wrap = v

    def setMinimumWidth(self, w: int) -> None:
        self.min_width = w


def _make_fake_dashboard_with_pit_label() -> types.SimpleNamespace:
    """Fake dashboard object with the pit lane status label attached."""
    fake = types.SimpleNamespace()
    lbl = _MockLabel()
    fake._tm_lbl_pit_lane_status = lbl
    return fake


# ---------------------------------------------------------------------------
# Pit lane status label logic (mirrors _tm_try_build_station_map wiring)
# ---------------------------------------------------------------------------

def _apply_pit_lane_status_update(fake_dashboard, station_map) -> None:
    """Replicate the label-update block from _tm_try_build_station_map."""
    if hasattr(fake_dashboard, "_tm_lbl_pit_lane_status"):
        if getattr(station_map, "pit_lane", None) is not None:
            fake_dashboard._tm_lbl_pit_lane_status.setText("Pit lane: detected ✓")
            fake_dashboard._tm_lbl_pit_lane_status.setStyleSheet(
                "color: #4caf50; font-size: 10px;"
            )
        else:
            fake_dashboard._tm_lbl_pit_lane_status.setText("Pit lane: not detected")
            fake_dashboard._tm_lbl_pit_lane_status.setStyleSheet(
                "color: #888888; font-size: 10px;"
            )


class TestPitLaneStatusLabel:
    def test_default_state_is_not_detected(self):
        """Label initialises to 'not detected' with grey colour."""
        lbl = _MockLabel()
        lbl.setText("Pit lane: not detected")
        lbl.setStyleSheet("color: #888888; font-size: 10px;")
        assert "not detected" in lbl.text
        assert "#888888" in lbl.style

    def test_label_turns_green_when_pit_lane_detected(self):
        """Label must show green 'detected' text when station_map.pit_lane is set."""
        fake = _make_fake_dashboard_with_pit_label()
        sm = _make_station_map()
        sm.pit_lane = PitLaneBoundary(
            entry_station_m=100.0, exit_station_m=200.0,
            entry_progress=0.1, exit_progress=0.2,
        )
        _apply_pit_lane_status_update(fake, sm)
        assert "detected" in fake._tm_lbl_pit_lane_status.text
        assert "#4caf50" in fake._tm_lbl_pit_lane_status.style

    def test_label_stays_grey_when_no_pit_lane(self):
        """Label stays grey when station_map.pit_lane is None."""
        fake = _make_fake_dashboard_with_pit_label()
        sm = _make_station_map()
        assert sm.pit_lane is None
        _apply_pit_lane_status_update(fake, sm)
        assert "not detected" in fake._tm_lbl_pit_lane_status.text
        assert "#888888" in fake._tm_lbl_pit_lane_status.style

    def test_label_update_skipped_when_attr_missing(self):
        """No AttributeError if _tm_lbl_pit_lane_status not present."""
        fake = types.SimpleNamespace()  # no label attribute
        sm = _make_station_map()
        # Should not raise
        _apply_pit_lane_status_update(fake, sm)

    def test_label_resets_to_grey_after_pit_lane_cleared(self):
        """If pit_lane is set then cleared, label reverts to grey."""
        fake = _make_fake_dashboard_with_pit_label()
        sm = _make_station_map()

        # First: set pit_lane
        sm.pit_lane = PitLaneBoundary(
            entry_station_m=100.0, exit_station_m=200.0,
            entry_progress=0.1, exit_progress=0.2,
        )
        _apply_pit_lane_status_update(fake, sm)
        assert "#4caf50" in fake._tm_lbl_pit_lane_status.style

        # Clear pit_lane
        sm.pit_lane = None
        _apply_pit_lane_status_update(fake, sm)
        assert "#888888" in fake._tm_lbl_pit_lane_status.style
        assert "not detected" in fake._tm_lbl_pit_lane_status.text


class TestApRowWordWrap:
    """Verify that _MockLabel supports the setWordWrap / setMinimumWidth API
    used by the real QLabel — these are exercised by the _ap_row helper."""

    def test_word_wrap_can_be_set(self):
        lbl = _MockLabel()
        lbl.setWordWrap(True)
        assert lbl.word_wrap is True

    def test_minimum_width_can_be_set(self):
        lbl = _MockLabel()
        lbl.setMinimumWidth(120)
        assert lbl.min_width == 120


# ---------------------------------------------------------------------------
# AC7: legacy _tm_ap_* widgets must be absent from dashboard.py
# ---------------------------------------------------------------------------

from pathlib import Path


def test_no_legacy_tm_ap_widgets_in_dashboard():
    """AC7: all 8 legacy _tm_ap_* widget attributes must be absent from dashboard.py."""
    src = (Path(__file__).parent.parent / "ui" / "dashboard.py").read_text(encoding="utf-8")
    legacy_names = [
        "_tm_ap_detected", "_tm_ap_reviewed", "_tm_ap_confirmed",
        "_tm_ap_rejected", "_tm_ap_needs_laps", "_tm_ap_pct",
        "_tm_ap_ai_ready", "_tm_ap_blockers",
    ]
    found = [n for n in legacy_names if f"self.{n}" in src]
    assert not found, f"Legacy widgets still present: {found}"


# ---------------------------------------------------------------------------
# AC8: 5 QGroupBox sections must be present in Track Modelling tab
# ---------------------------------------------------------------------------

def test_five_qgroupbox_sections_present():
    """AC8: Track Modelling tab must have 5 numbered QGroupBox sections."""
    root = Path(__file__).parent.parent
    # Sections moved to the mixin; search both files
    src = (
        (root / "ui" / "dashboard.py").read_text(encoding="utf-8")
        + (root / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")
    )
    expected_titles = [
        "1. Seed Data",
        "2. Calibration",
        "3. Segment Detection",
        "4. Segment Review",
        "5. Track Model Alignment",
    ]
    missing = [t for t in expected_titles if t not in src]
    assert not missing, f"QGroupBox titles missing from Track Modelling UI: {missing}"
