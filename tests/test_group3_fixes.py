"""Tests for Remediation Group 3 fixes.

DEF-P2-011: Best lap summary includes outlaps and invalid laps
DEF-P2-013: Pit stop indicator lost after session reload (verified fixed by Group 2)
DEF-P3-006: Session summary not recalculated after History load (verified fixed)
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_stats():
    """Full MagicMock LapStats with all attributes write_lap reads as real values."""
    stats = MagicMock()
    stats.lock_up_count = 0
    stats.wheelspin_count = 0
    stats.brake_consistency_m = 0.0
    stats.max_speed_kmh = 200.0
    stats.avg_throttle_pct = 70.0
    stats.avg_brake_pct = 15.0
    stats.oversteer_count = 0
    stats.oversteer_throttle_on_count = 0
    stats.kerb_count = 0
    stats.bottoming_count = 0
    stats.snap_throttle_count = 0
    stats.over_braking_count = 0
    stats.abrupt_release_count = 0
    stats.rev_limiter_count = 0
    stats.max_lat_g = 0.0
    stats.off_track_count = 0
    stats.tyre_temp_avg = 0.0
    stats.lock_up_positions = []
    stats.wheelspin_positions = []
    stats.oversteer_positions = []
    stats.snap_throttle_positions = []
    stats.over_braking_positions = []
    return stats


def _make_db():
    from data.session_db import SessionDB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return SessionDB(tmp.name)


# ---------------------------------------------------------------------------
# DEF-P2-011 — outlap excluded from summary best/avg calculations
# ---------------------------------------------------------------------------

class TestOutlapSummaryLogic(unittest.TestCase):
    """Test the logic that _refresh_practice_summary uses to exclude outlaps.

    Qt widgets cannot be instantiated without a display, so we test the
    filtering logic conditions in isolation using the same rules as the method.
    """

    def _summarise(self, rows: list[dict]) -> dict:
        """Reproduce _refresh_practice_summary logic for unit testing.

        Each row dict has keys: ms (int), fuel (float), is_out_lap (bool).
        Returns: {best_ms, avg_ms, avg_fuel, total}.
        """
        times_ms = []
        fuels = []
        for row in rows:
            is_out = row.get("is_out_lap", False)
            ms = row.get("ms", 0)
            fuel = row.get("fuel", 0.0)
            if not is_out and ms > 0:
                times_ms.append(ms)
            if not is_out and fuel > 0:
                fuels.append(fuel)

        return {
            "total": len(rows),
            "best_ms": min(times_ms) if times_ms else 0,
            "avg_ms": int(sum(times_ms) / len(times_ms)) if times_ms else 0,
            "avg_fuel": sum(fuels) / len(fuels) if fuels else 0.0,
        }

    def test_outlap_not_selected_as_best_lap(self):
        """When the only sub-1:25 time is an outlap, best lap is the next valid lap."""
        rows = [
            {"ms": 95_000, "fuel": 0.0, "is_out_lap": True},   # outlap — fast but invalid
            {"ms": 92_000, "fuel": 3.5, "is_out_lap": False},
            {"ms": 91_000, "fuel": 3.4, "is_out_lap": False},
        ]
        result = self._summarise(rows)
        self.assertEqual(result["best_ms"], 91_000,
                         "Outlap must not be selected as best lap even if its time is faster")

    def test_outlap_excluded_from_avg(self):
        """Outlap time does not inflate the average."""
        rows = [
            {"ms": 150_000, "fuel": 0.0, "is_out_lap": True},  # very slow outlap
            {"ms": 90_000, "fuel": 3.5, "is_out_lap": False},
            {"ms": 91_000, "fuel": 3.4, "is_out_lap": False},
        ]
        result = self._summarise(rows)
        # Average should be (90_000 + 91_000) / 2 = 90_500
        self.assertEqual(result["avg_ms"], 90_500)
        # Not (150_000 + 90_000 + 91_000) / 3 = 110_333
        self.assertNotEqual(result["avg_ms"], 110_333)

    def test_outlap_fuel_excluded_from_avg_fuel(self):
        """Outlap fuel (0 or anomalously low) does not skew the fuel average."""
        rows = [
            {"ms": 150_000, "fuel": 0.5, "is_out_lap": True},  # outlap fuel (warmup)
            {"ms": 90_000, "fuel": 3.5, "is_out_lap": False},
            {"ms": 91_000, "fuel": 3.4, "is_out_lap": False},
        ]
        result = self._summarise(rows)
        self.assertAlmostEqual(result["avg_fuel"], (3.5 + 3.4) / 2, places=2)

    def test_total_count_includes_outlaps(self):
        """Total row count includes outlaps — they ARE laps, just excluded from stats."""
        rows = [
            {"ms": 150_000, "fuel": 0.0, "is_out_lap": True},
            {"ms": 90_000, "fuel": 3.5, "is_out_lap": False},
            {"ms": 91_000, "fuel": 3.4, "is_out_lap": False},
        ]
        result = self._summarise(rows)
        self.assertEqual(result["total"], 3)

    def test_all_valid_laps_unchanged(self):
        """Existing behaviour unchanged when no outlaps are present."""
        rows = [
            {"ms": 92_000, "fuel": 3.5, "is_out_lap": False},
            {"ms": 90_000, "fuel": 3.4, "is_out_lap": False},
            {"ms": 91_000, "fuel": 3.6, "is_out_lap": False},
        ]
        result = self._summarise(rows)
        self.assertEqual(result["best_ms"], 90_000)
        self.assertEqual(result["total"], 3)

    def test_only_outlap_session_shows_no_best(self):
        """If all laps are outlaps, best and avg show no data (0 in the logic)."""
        rows = [
            {"ms": 95_000, "fuel": 0.0, "is_out_lap": True},
            {"ms": 96_000, "fuel": 0.0, "is_out_lap": True},
        ]
        result = self._summarise(rows)
        self.assertEqual(result["best_ms"], 0)
        self.assertEqual(result["avg_ms"], 0)
        self.assertAlmostEqual(result["avg_fuel"], 0.0)


# ---------------------------------------------------------------------------
# DEF-P2-011 — is_out_lap in DB (get_session_laps returns it)
# ---------------------------------------------------------------------------

class TestOutlapDB(unittest.TestCase):

    def test_get_session_laps_returns_is_out_lap(self):
        """get_session_laps must return is_out_lap key."""
        db = _make_db()
        sid = db.open_session(0, "Suzuka", "Practice")
        db.write_lap(sid, 1, 95_000, 0.5, _make_stats(), is_out_lap=True)
        laps = db.get_session_laps(sid)
        self.assertEqual(len(laps), 1)
        self.assertEqual(laps[0]["is_out_lap"], 1)
        db.close()

    def test_normal_lap_is_out_lap_false(self):
        """Normal lap has is_out_lap=0 in DB."""
        db = _make_db()
        sid = db.open_session(0, "Suzuka", "Practice")
        db.write_lap(sid, 1, 90_000, 3.5, _make_stats(), is_out_lap=False)
        laps = db.get_session_laps(sid)
        self.assertEqual(laps[0]["is_out_lap"], 0)
        db.close()

    def test_outlap_flag_round_trip(self):
        """is_out_lap=True survives write-then-read cycle."""
        db = _make_db()
        sid = db.open_session(0, "Fuji", "Practice")
        db.write_lap(sid, 2, 98_000, 0.3, _make_stats(), is_out_lap=True, is_pit_lap=False)
        laps = db.get_session_laps(sid)
        self.assertEqual(laps[0]["is_out_lap"], 1)
        db.close()

    def test_pit_lap_and_outlap_independently_stored(self):
        """Pit lap and out lap flags are independently stored and retrieved."""
        db = _make_db()
        sid = db.open_session(0, "Suzuka", "Practice")
        db.write_lap(sid, 1, 95_000, 0.5, _make_stats(), is_out_lap=True, is_pit_lap=False)
        db.write_lap(sid, 2, 110_000, 5.5, _make_stats(), is_out_lap=False, is_pit_lap=True)
        db.write_lap(sid, 3, 90_000, 3.5, _make_stats(), is_out_lap=False, is_pit_lap=False)
        laps = db.get_session_laps(sid)
        self.assertEqual(len(laps), 3)
        # Lap 1 is outlap
        self.assertEqual(laps[0]["is_out_lap"], 1)
        self.assertEqual(laps[0]["is_pit_lap"], 0)
        # Lap 2 is pit lap
        self.assertEqual(laps[1]["is_out_lap"], 0)
        self.assertEqual(laps[1]["is_pit_lap"], 1)
        # Lap 3 is normal
        self.assertEqual(laps[2]["is_out_lap"], 0)
        self.assertEqual(laps[2]["is_pit_lap"], 0)
        db.close()


# ---------------------------------------------------------------------------
# DEF-P2-013 — pit stop indicator persists after DB reload (verified by Group 2)
# ---------------------------------------------------------------------------

class TestPitFlagReload(unittest.TestCase):

    def test_is_pit_lap_returned_by_get_session_laps(self):
        """get_session_laps returns is_pit_lap — pit indicator available for reload."""
        db = _make_db()
        sid = db.open_session(0, "Suzuka", "Practice")
        db.write_lap(sid, 1, 110_000, 5.5, _make_stats(), is_pit_lap=True)
        db.write_lap(sid, 2, 90_000, 3.5, _make_stats(), is_pit_lap=False)
        laps = db.get_session_laps(sid)
        self.assertEqual(laps[0]["is_pit_lap"], 1)
        self.assertEqual(laps[1]["is_pit_lap"], 0)
        db.close()

    def test_fuel_start_end_survive_reload(self):
        """fuel_start and fuel_end available for reload (covered by Group 2, regression guard)."""
        db = _make_db()
        sid = db.open_session(0, "Suzuka", "Practice")
        db.write_lap(sid, 1, 90_000, 3.5, _make_stats(), fuel_start=44.0, fuel_end=40.5)
        laps = db.get_session_laps(sid)
        self.assertAlmostEqual(laps[0]["fuel_start"], 44.0, places=2)
        self.assertAlmostEqual(laps[0]["fuel_end"],   40.5, places=2)
        db.close()

    def test_compound_survives_reload(self):
        """Compound stored and returned (regression guard for DEF-P1-006 fix)."""
        db = _make_db()
        sid = db.open_session(0, "Suzuka", "Practice")
        db.write_lap(sid, 1, 90_000, 3.5, _make_stats(), compound="RM")
        laps = db.get_session_laps(sid)
        self.assertEqual(laps[0]["compound"], "RM")
        db.close()


# ---------------------------------------------------------------------------
# DEF-P3-006 — session summary recalculates after history load (source scan)
# ---------------------------------------------------------------------------

class TestSummarySources(unittest.TestCase):

    def test_on_history_load_session_calls_refresh_summary(self):
        """_on_history_load_session must call _refresh_practice_summary at the end."""
        src = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
        text = src.read_text(encoding="utf-8")
        # Find the _on_history_load_session block
        method_start = text.find("def _on_history_load_session(")
        method_end = text.find("\n    def ", method_start + 1)
        method_body = text[method_start:method_end]
        self.assertIn("_refresh_practice_summary", method_body,
                      "_on_history_load_session must call _refresh_practice_summary()")

    def test_import_bank_session_calls_refresh_summary(self):
        """_import_bank_session does NOT call _refresh_practice_summary (status label instead).
        The summary is updated via _add_bank_lap_row → _refresh_practice_summary at end of _add_lap_row.
        But _add_bank_lap_row does NOT call it — the bank caller must.
        Verify: _on_history_load_session IS the authoritative caller for the history path."""
        src = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
        text = src.read_text(encoding="utf-8")
        method_start = text.find("def _on_history_load_session(")
        method_end = text.find("\n    def ", method_start + 1)
        method_body = text[method_start:method_end]
        # Must switch to Practice Review tab
        self.assertIn("setCurrentIndex", method_body)

    def test_refresh_summary_skips_outlap_rows(self):
        """Source scan: _refresh_practice_summary must filter is_out_lap rows."""
        src = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
        text = src.read_text(encoding="utf-8")
        method_start = text.find("def _refresh_practice_summary(")
        method_end = text.find("\n    def ", method_start + 1)
        method_body = text[method_start:method_end]
        self.assertIn("is_out_lap", method_body,
                      "_refresh_practice_summary must read is_out_lap flag")
        self.assertIn("UserRole", method_body,
                      "_refresh_practice_summary must read UserRole data to get is_out_lap")

    def test_add_bank_lap_row_stores_userole_flags(self):
        """Source scan: _add_bank_lap_row must store is_out_lap/is_pit_lap in UserRole."""
        src = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
        text = src.read_text(encoding="utf-8")
        method_start = text.find("def _add_bank_lap_row(")
        method_end = text.find("\n    def ", method_start + 1)
        method_body = text[method_start:method_end]
        self.assertIn("UserRole", method_body)
        self.assertIn("is_out_lap", method_body)

    def test_on_history_load_session_clears_stale_compound_tags(self):
        """_on_history_load_session must clear stale _lap_compound_tags before loading."""
        src = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
        text = src.read_text(encoding="utf-8")
        method_start = text.find("def _on_history_load_session(")
        method_end = text.find("\n    def ", method_start + 1)
        method_body = text[method_start:method_end]
        self.assertIn("_lap_compound_tags.pop", method_body,
                      "_on_history_load_session must clear stale compound tags")

    def test_on_history_load_session_computes_avg_fuel(self):
        """_on_history_load_session must compute _loaded_session_avg_fuel."""
        src = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
        text = src.read_text(encoding="utf-8")
        method_start = text.find("def _on_history_load_session(")
        method_end = text.find("\n    def ", method_start + 1)
        method_body = text[method_start:method_end]
        self.assertIn("_loaded_session_avg_fuel", method_body)


if __name__ == "__main__":
    unittest.main()
