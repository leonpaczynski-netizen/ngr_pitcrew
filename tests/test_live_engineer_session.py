"""Session-type-aware live engineer — talks feel in practice, one-lap pace in
qualifying, and defers to the strategy engine in a race (like a real engineer).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.live_engineer_session import (
    normalise_session_mode, session_engineer_call, PRACTICE, QUALIFYING, RACE,
)


class TestModeNormalisation:
    def test_race_from_phase(self):
        assert normalise_session_mode(None, "RACING") == RACE
    def test_qualifying(self):
        assert normalise_session_mode("qualifying") == QUALIFYING
    def test_default_is_practice(self):
        assert normalise_session_mode(None) == PRACTICE
        assert normalise_session_mode("") == PRACTICE


class TestRaceDefersToStrategy:
    def test_race_returns_empty(self):
        assert session_engineer_call(RACE, connected=True, lap_count=5) == ""


class TestNoTelemetry:
    def test_disconnected_is_silent(self):
        assert session_engineer_call(PRACTICE, connected=False, lap_count=3) == ""


class TestPractice:
    def test_talks_feel_not_strategy(self):
        msg = session_engineer_call(PRACTICE, connected=True, lap_count=5)
        assert "balance" in msg.lower()
        for banned in ("fuel", "pit", "stop", "stint"):
            assert banned not in msg.lower()

    def test_early_laps_ask_for_a_read(self):
        assert "clean lap" in session_engineer_call(PRACTICE, connected=True, lap_count=0).lower()
        assert "rhythm" in session_engineer_call(PRACTICE, connected=True, lap_count=1).lower()


class TestQualifying:
    def test_out_lap_builds_temperature(self):
        msg = session_engineer_call(QUALIFYING, connected=True, lap_count=0)
        assert "temperature" in msg.lower() and "flying lap" in msg.lower()

    def test_flying_lap_says_commit(self):
        msg = session_engineer_call(QUALIFYING, connected=True, lap_count=2,
                                    last_lap_s=95.2, best_lap_s=94.0)
        assert "commit" in msg.lower()
        for banned in ("fuel", "pit", "stint"):
            assert banned not in msg.lower()

    def test_personal_best_is_called_out(self):
        msg = session_engineer_call(QUALIFYING, connected=True, lap_count=3,
                                    last_lap_s=93.5, best_lap_s=93.5)
        assert "personal best" in msg.lower() and "93.5" in msg
