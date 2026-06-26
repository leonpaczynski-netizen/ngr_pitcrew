"""Tests for Qualifying Mode completion feature.

Covers:
- Voice delta announcements after a qualifying lap
- Flying-lap tyre-warning suppression
- get_best_practice_lap_ms DB method

No Qt, no audio. Announcer stubs only.
"""
from __future__ import annotations

import sys
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub audio / COM modules so the announcer module can be imported headlessly
# ---------------------------------------------------------------------------

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

from voice.announcer import VoiceAnnouncer, AnnouncerEventHandler  # noqa: E402
from telemetry.state import TyreState                               # noqa: E402
from data.session_db import SessionDB                               # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_announcer(session_mode: str = "qualifying",
                    target_ms: int = 0) -> VoiceAnnouncer:
    cfg = {"enabled": True, "rate": 175, "volume": 1.0}
    ann = VoiceAnnouncer(cfg)
    ann._session_mode = session_mode
    ann._qualifying_target_ms = target_ms
    return ann


class _FakeLapRecord:
    """Minimal stand-in for a LapRecord / data record."""
    def __init__(self, lap_time_ms: int, lap_num: int = 1, delta_ms: int = 0):
        self.lap_time_ms = lap_time_ms
        self.lap_num = lap_num
        self.delta_ms = delta_ms


def _make_handler(session_mode: str = "qualifying",
                  target_ms: int = 0,
                  qualifying_lap_count: int = 0) -> tuple[AnnouncerEventHandler, list[str]]:
    """Returns (handler, announced_texts).  handler._a.announce is spied on."""
    ann = _make_announcer(session_mode, target_ms)
    announced: list[str] = []

    def _spy(text, priority, cooldown_key, cooldown_secs=0.0, **kw):
        announced.append(text)

    ann.announce = _spy  # type: ignore[method-assign]
    handler = AnnouncerEventHandler(ann)
    handler._qualifying_lap_count = qualifying_lap_count
    return handler, announced


def _db() -> SessionDB:
    return SessionDB(":memory:")


# ---------------------------------------------------------------------------
# 1. Delta voice — faster than target
# ---------------------------------------------------------------------------

class TestDeltaVoice:

    def test_delta_voice_faster_than_target(self):
        """lap_ms < target_ms → phrase contains 'under target'."""
        handler, announced = _make_handler(target_ms=91000)
        record = _FakeLapRecord(lap_time_ms=90000)
        handler._on_lap({"record": record, "has_best": True, "laps_remaining": 0})
        delta_phrases = [t for t in announced if "under target" in t or "over target" in t or "On target" in t]
        assert any("under target" in p for p in delta_phrases), f"announced: {announced}"

    def test_delta_voice_slower_than_target(self):
        """lap_ms > target_ms → phrase contains 'over target'."""
        handler, announced = _make_handler(target_ms=91000)
        record = _FakeLapRecord(lap_time_ms=92000)
        handler._on_lap({"record": record, "has_best": True, "laps_remaining": 0})
        assert any("over target" in p for p in announced), f"announced: {announced}"

    def test_delta_voice_on_target(self):
        """lap_ms == target_ms → exact phrase 'Lap complete. On target.'"""
        handler, announced = _make_handler(target_ms=91000)
        record = _FakeLapRecord(lap_time_ms=91000)
        handler._on_lap({"record": record, "has_best": True, "laps_remaining": 0})
        assert "Lap complete. On target." in announced, f"announced: {announced}"

    def test_delta_voice_suppressed_no_lap_time(self):
        """lap_ms == 0 → no qualifying delta announcement."""
        handler, announced = _make_handler(target_ms=91000)
        record = _FakeLapRecord(lap_time_ms=0)
        handler._on_lap({"record": record, "has_best": True, "laps_remaining": 0})
        delta_phrases = [t for t in announced if "under target" in t or "over target" in t or "On target" in t]
        assert len(delta_phrases) == 0, f"unexpected delta announcement: {delta_phrases}"

    def test_delta_voice_suppressed_no_target(self):
        """target_ms == 0 → no qualifying delta announcement."""
        handler, announced = _make_handler(target_ms=0)
        record = _FakeLapRecord(lap_time_ms=91000)
        handler._on_lap({"record": record, "has_best": True, "laps_remaining": 0})
        delta_phrases = [t for t in announced if "under target" in t or "over target" in t or "On target" in t]
        assert len(delta_phrases) == 0, f"unexpected delta announcement: {delta_phrases}"


# ---------------------------------------------------------------------------
# 6–7. Flying lap suppression of tyre warnings
# ---------------------------------------------------------------------------

class TestFlyingLapTyreSuppression:

    def test_flying_lap_suppresses_tyre_warning(self):
        """qualifying_lap_count >= 1 → _on_tyre returns without announcing."""
        handler, announced = _make_handler(qualifying_lap_count=1)
        data = {"label": "front left", "new_state": TyreState.OVERHEATING}
        handler._on_tyre(data)
        assert len(announced) == 0, f"tyre warning should be suppressed: {announced}"

    def test_not_flying_lap_allows_tyre_warning(self):
        """qualifying_lap_count == 0 → _on_tyre proceeds and announces."""
        handler, announced = _make_handler(qualifying_lap_count=0)
        data = {"label": "front left", "new_state": TyreState.OVERHEATING}
        handler._on_tyre(data)
        assert len(announced) > 0, "tyre warning should be announced on outlap"


# ---------------------------------------------------------------------------
# 8–10. get_best_practice_lap_ms DB tests
# ---------------------------------------------------------------------------

class TestGetBestPracticeLapMs:

    def _setup_db_with_car_session(self, db: SessionDB,
                                   car_name: str = "TestCar",
                                   track: str = "TestTrack") -> tuple[int, int]:
        """Insert a car and open a practice session. Returns (car_id, session_id)."""
        car_id = db.upsert_car({"name": car_name})
        session_id = db.open_session(
            car_id=car_id,
            track=track,
            session_type="practice",
            car_name=car_name,
        )
        return car_id, session_id

    def test_get_best_practice_lap_ms_happy_path(self):
        """Two practice laps (800 ms, 900 ms) → returns 800."""
        db = _db()
        try:
            car_id, sid = self._setup_db_with_car_session(db)
            db.write_lap(sid, 1, 800, 0.0, None, session_type="Practice")
            db.write_lap(sid, 2, 900, 0.0, None, session_type="Practice")
            result = db.get_best_practice_lap_ms(car_id, "TestTrack")
            assert result == 800
        finally:
            db.close()

    def test_get_best_practice_lap_ms_excludes_pit_laps(self):
        """Normal lap 800 ms + pit lap 700 ms → returns 800 (pit excluded)."""
        db = _db()
        try:
            car_id, sid = self._setup_db_with_car_session(db)
            db.write_lap(sid, 1, 800, 0.0, None, session_type="Practice", is_pit_lap=False)
            db.write_lap(sid, 2, 700, 0.0, None, session_type="Practice", is_pit_lap=True)
            result = db.get_best_practice_lap_ms(car_id, "TestTrack")
            assert result == 800
        finally:
            db.close()

    def test_get_best_practice_lap_ms_no_data(self):
        """Empty DB → None."""
        db = _db()
        try:
            result = db.get_best_practice_lap_ms(99, "NoTrack")
            assert result is None
        finally:
            db.close()
