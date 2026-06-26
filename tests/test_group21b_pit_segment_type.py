"""Tests for TrackSegmentType.PIT_LANE — Group 21B."""
import pytest
from data.track_segment_detection import TrackSegmentType


def test_pit_lane_value():
    """PIT_LANE enum member should exist with value 'pit_lane'."""
    assert TrackSegmentType.PIT_LANE == "pit_lane"
    assert TrackSegmentType.PIT_LANE.value == "pit_lane"


def test_pit_lane_roundtrip():
    """TrackSegmentType('pit_lane') should deserialise to PIT_LANE."""
    result = TrackSegmentType("pit_lane")
    assert result is TrackSegmentType.PIT_LANE


def test_unknown_value_raises():
    """Constructing TrackSegmentType with an unknown value must raise ValueError."""
    with pytest.raises(ValueError):
        TrackSegmentType("unknown_segment_xyz")
