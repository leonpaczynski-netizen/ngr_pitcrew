"""Unit tests for telemetry.listener.UDPListener (AC1).

Tests are constructed without calling start() so no socket is bound and no
thread is spawned.  Internal deque/event state is manipulated directly.
"""
from __future__ import annotations

import time
from collections import deque

import pytest


class TestUDPListenerPacketRate:
    """packet_rate property."""

    def _make_listener(self):
        from telemetry.listener import UDPListener
        return UDPListener("0.0.0.0", 33741, lambda b: None)

    def test_packet_rate_with_multiple_timestamps(self):
        listener = self._make_listener()
        # Inject 5 timestamps spanning 4 seconds → rate = (5-1)/4 = 1.0 pps
        base = time.monotonic()
        for i in range(5):
            listener._packet_timestamps.append(base + i)
        rate = listener.packet_rate
        assert abs(rate - 1.0) < 1e-6

    def test_packet_rate_two_timestamps(self):
        listener = self._make_listener()
        base = time.monotonic()
        listener._packet_timestamps.append(base)
        listener._packet_timestamps.append(base + 2.0)
        # (2 - 1) / 2.0 = 0.5
        assert abs(listener.packet_rate - 0.5) < 1e-6

    def test_packet_rate_zero_timestamps(self):
        listener = self._make_listener()
        assert listener.packet_rate == 0.0

    def test_packet_rate_one_timestamp(self):
        listener = self._make_listener()
        listener._packet_timestamps.append(time.monotonic())
        assert listener.packet_rate == 0.0


class TestUDPListenerConnected:
    """connected property reflects _connected bool directly."""

    def _make_listener(self):
        from telemetry.listener import UDPListener
        return UDPListener("0.0.0.0", 33741, lambda b: None)

    def test_connected_true_when_flag_set(self):
        listener = self._make_listener()
        listener._connected = True
        assert listener.connected is True

    def test_connected_false_when_flag_clear(self):
        listener = self._make_listener()
        listener._connected = False
        assert listener.connected is False


class TestUDPListenerErrors:
    """increment_errors and parse_errors / total_received."""

    def _make_listener(self):
        from telemetry.listener import UDPListener
        return UDPListener("0.0.0.0", 33741, lambda b: None)

    def test_parse_errors_increments(self):
        listener = self._make_listener()
        listener.increment_errors()
        listener.increment_errors()
        listener.increment_errors()
        assert listener.parse_errors == 3

    def test_total_received_starts_at_zero(self):
        listener = self._make_listener()
        assert listener.total_received == 0

    def test_total_received_reflects_internal_counter(self):
        listener = self._make_listener()
        listener._total_received = 5
        assert listener.total_received == 5
        listener._total_received += 1
        assert listener.total_received == 6


class TestUDPListenerStop:
    """stop() sets the stop event."""

    def test_stop_sets_event(self):
        from telemetry.listener import UDPListener
        listener = UDPListener("0.0.0.0", 33741, lambda b: None)
        assert not listener._stop_event.is_set()
        listener.stop()
        assert listener._stop_event.is_set()
