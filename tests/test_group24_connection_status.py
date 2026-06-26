"""Tests for Group 24 AC4 — packet-age-wins connection status."""
import time
import pytest


class FakeStatusBar:
    def __init__(self):
        self.connected_calls = []
        self.disconnected_calls = 0

    def set_connected(self, hz):
        self.connected_calls.append(hz)

    def set_disconnected(self):
        self.disconnected_calls += 1

    def set_race_state(self, text):
        pass


class FakeDashboard:
    """Minimal stub replicating on_connection_status with packet-age guard."""

    def __init__(self, last_packet_received=0.0):
        self._last_packet_received = last_packet_received
        self._status_bar = FakeStatusBar()

    def on_connection_status(self, connected: bool, hz: float) -> None:
        if not connected:
            last = getattr(self, "_last_packet_received", 0.0)
            if time.time() - last < 3.0:
                return  # recent packet — suppress spurious disconnect
        if connected:
            self._status_bar.set_connected(hz)
        else:
            self._status_bar.set_disconnected()


def test_disconnect_suppressed_when_recent_packet():
    """set_disconnected NOT called when last packet was < 3 s ago."""
    dash = FakeDashboard(last_packet_received=time.time() - 1.0)
    dash.on_connection_status(False, 0)
    assert dash._status_bar.disconnected_calls == 0


def test_disconnect_fires_when_packet_stale():
    """set_disconnected IS called when last packet was > 3 s ago."""
    dash = FakeDashboard(last_packet_received=time.time() - 4.0)
    dash.on_connection_status(False, 0)
    assert dash._status_bar.disconnected_calls == 1


def test_disconnect_fires_when_never_received():
    """set_disconnected IS called when _last_packet_received is 0.0 (never set)."""
    dash = FakeDashboard(last_packet_received=0.0)
    dash.on_connection_status(False, 0)
    assert dash._status_bar.disconnected_calls == 1


def test_connect_always_fires():
    """set_connected IS called regardless of packet age when connected=True."""
    dash = FakeDashboard(last_packet_received=time.time() - 0.5)
    dash.on_connection_status(True, 60)
    assert dash._status_bar.connected_calls == [60]
    assert dash._status_bar.disconnected_calls == 0
