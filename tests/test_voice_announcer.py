"""Unit tests for voice.announcer (AC4).

Audio / COM modules are stubbed in sys.modules before any import so the test
suite runs on any OS without win32com, pythoncom, sounddevice, winsound, or
pyttsx3 installed.  VoiceAnnouncer.start() is never called.
"""
from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub audio / COM modules before importing the announcer module
# ---------------------------------------------------------------------------

# Only stub modules that cannot be imported natively.
# This avoids overwriting real numpy / sounddevice / winsound in sys.modules,
# which would corrupt tests that run later in the same pytest session.
def _try_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False

for _mod in ("win32com", "win32com.client", "pythoncom",
             "sounddevice", "winsound", "pyttsx3", "numpy"):
    if _mod not in sys.modules and not _try_import(_mod):
        sys.modules[_mod] = MagicMock()

# Now safe to import
from voice.announcer import VoiceAnnouncer, AnnouncerEventHandler  # noqa: E402
from telemetry.state import EventType, Priority, TelemetryEvent    # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_announcer(enabled=True, **extra):
    cfg = {"enabled": enabled, "rate": 175, "volume": 1.0}
    cfg.update(extra)
    return VoiceAnnouncer(cfg)


def _make_event(event_type, data=None, priority=Priority.LOW):
    return TelemetryEvent(type=event_type, data=data or {}, priority=priority)


# ---------------------------------------------------------------------------
# VoiceAnnouncer.announce()
# ---------------------------------------------------------------------------

class TestAnnounce:
    def test_announce_enqueues_item(self):
        ann = _make_announcer()
        ann.announce("test message", Priority.LOW, "test_key")
        assert ann._queue.qsize() == 1

    def test_announce_disabled_does_not_enqueue(self):
        ann = _make_announcer(enabled=False)
        ann.announce("test message", Priority.LOW, "test_key")
        assert ann._queue.qsize() == 0


# ---------------------------------------------------------------------------
# VoiceAnnouncer._on_cooldown()
# ---------------------------------------------------------------------------

class TestOnCooldown:
    def test_on_cooldown_false_when_key_absent(self):
        ann = _make_announcer()
        assert ann._on_cooldown("nonexistent_key") is False

    def test_on_cooldown_true_when_future_expiry(self):
        ann = _make_announcer()
        ann._cooldowns["my_key"] = time.monotonic() + 60.0
        assert ann._on_cooldown("my_key") is True

    def test_on_cooldown_false_when_expired(self):
        ann = _make_announcer()
        ann._cooldowns["my_key"] = time.monotonic() - 1.0
        assert ann._on_cooldown("my_key") is False


# ---------------------------------------------------------------------------
# VoiceAnnouncer._is_stale()
# ---------------------------------------------------------------------------

class TestIsStale:
    def _make_announcement(self, version_key="", version_num=0):
        from voice.announcer import Announcement
        return Announcement(
            priority=Priority.LOW.value,
            seq=0,
            text="hello",
            cooldown_key="k",
            cooldown_secs=0.0,
            version_key=version_key,
            version_num=version_num,
        )

    def test_is_stale_false_when_no_version_key(self):
        ann = _make_announcer()
        item = self._make_announcement(version_key="", version_num=0)
        assert ann._is_stale(item) is False

    def test_is_stale_true_when_newer_version_exists(self):
        ann = _make_announcer()
        ann._versions["pos"] = 5
        item = self._make_announcement(version_key="pos", version_num=3)
        assert ann._is_stale(item) is True

    def test_is_stale_false_when_version_current(self):
        ann = _make_announcer()
        ann._versions["pos"] = 2
        item = self._make_announcement(version_key="pos", version_num=2)
        assert ann._is_stale(item) is False


# ---------------------------------------------------------------------------
# mute_for / clear_mute
# ---------------------------------------------------------------------------

class TestMute:
    def test_mute_for_sets_future_time(self):
        ann = _make_announcer()
        before = time.time()
        ann.mute_for(30)
        assert ann._muted_until > before + 29

    def test_clear_mute_sets_zero(self):
        ann = _make_announcer()
        ann.mute_for(30)
        ann.clear_mute()
        assert ann._muted_until == 0.0


# ---------------------------------------------------------------------------
# silence()
# ---------------------------------------------------------------------------

class TestSilence:
    def test_silence_clears_queue_and_puts_sentinel(self):
        ann = _make_announcer()
        ann.announce("first", Priority.LOW, "k1")
        ann.announce("second", Priority.LOW, "k2")
        ann.announce("third", Priority.LOW, "k3")
        assert ann._queue.qsize() == 3
        ann.silence()
        # Queue should now have exactly 1 item (the sentinel)
        assert ann._queue.qsize() == 1


# ---------------------------------------------------------------------------
# queue_depth
# ---------------------------------------------------------------------------

class TestQueueDepth:
    def test_queue_depth_returns_correct_count(self):
        ann = _make_announcer()
        ann.announce("one", Priority.LOW, "k1")
        ann.announce("two", Priority.LOW, "k2")
        assert ann.queue_depth == 2


# ---------------------------------------------------------------------------
# AnnouncerEventHandler routing
# ---------------------------------------------------------------------------

class TestAnnouncerEventHandler:
    def test_lap_completed_routes_to_on_lap_and_calls_announce(self):
        ann = _make_announcer()
        ann.announce = MagicMock()  # spy on announce

        handler = AnnouncerEventHandler(ann)
        data = {
            "record": MagicMock(lap_num=5, delta_ms=500),
            "has_best": True,
            "laps_remaining": 10,
            "remaining_time_ms": -1,
        }
        event = TelemetryEvent(type=EventType.LAP_COMPLETED, data=data,
                               priority=Priority.LOW)
        handler.handle(event)
        assert ann.announce.called

    def test_fuel_low_not_called_in_practice_mode(self):
        ann = _make_announcer()
        ann.set_session_mode("practice")
        ann.announce = MagicMock()

        handler = AnnouncerEventHandler(ann)
        data = {"fuel_laps": 2.5, "laps_remaining": 0}
        event = TelemetryEvent(type=EventType.FUEL_LOW, data=data,
                               priority=Priority.LOW)
        handler.handle(event)
        ann.announce.assert_not_called()

    def test_fuel_low_called_in_race_mode(self):
        ann = _make_announcer()
        ann.set_session_mode("race")
        ann.announce = MagicMock()

        handler = AnnouncerEventHandler(ann)
        data = {"fuel_laps": 2.5, "laps_remaining": 0}
        event = TelemetryEvent(type=EventType.FUEL_LOW, data=data,
                               priority=Priority.LOW)
        handler.handle(event)
        assert ann.announce.called
