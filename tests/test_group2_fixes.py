"""Tests for Remediation Group 2 fixes.

DEF-P1-005: Practice Analysis sends full setup despite BoP/tuning restrictions
DEF-P1-006: Tyre compound lap counts wrong — stale _lap_compound_tags from prior session
DEF-P1-007: Fuel burn uses live tracker avg even when historical session is loaded
DEF-P2-012: Tyre wear multiplier may come from stale source
DEF-P2-014: fuel_start / fuel_end not persisted to DB or returned by get_session_laps
DEF-P2-016: Practice Analysis calls AI without validating input data
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest
from dataclasses import dataclass, field
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_stats():
    """Create a MagicMock LapStats with all attributes write_lap accesses set to real values.
    MagicMock auto-creates any attribute access, so we must explicitly set every
    field that write_lap reads, otherwise getattr returns a MagicMock — not 0."""
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


# ---------------------------------------------------------------------------
# DEF-P2-014 — fuel_start / fuel_end persisted to DB and returned by get_session_laps
# ---------------------------------------------------------------------------

class TestFuelStartEndDB(unittest.TestCase):

    def _make_db(self):
        from data.session_db import SessionDB
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        return SessionDB(tmp.name)

    def _make_stats(self):
        return _make_stats()

    def test_write_lap_accepts_fuel_start_end(self):
        """write_lap should not raise when fuel_start and fuel_end are passed."""
        db = self._make_db()
        sid = db.open_session(0, "Suzuka", "Practice")
        lap_id = db.write_lap(
            sid, 1, 90_000, 3.5, self._make_stats(),
            fuel_start=45.0, fuel_end=41.5,
        )
        self.assertGreater(lap_id, 0)
        db.close()

    def test_get_session_laps_returns_fuel_start_end(self):
        """get_session_laps must return fuel_start and fuel_end keys."""
        db = self._make_db()
        sid = db.open_session(0, "Suzuka", "Practice")
        db.write_lap(sid, 1, 90_000, 3.5, self._make_stats(),
                     fuel_start=45.0, fuel_end=41.5)
        laps = db.get_session_laps(sid)
        self.assertEqual(len(laps), 1)
        self.assertAlmostEqual(laps[0]["fuel_start"], 45.0, places=2)
        self.assertAlmostEqual(laps[0]["fuel_end"], 41.5, places=2)
        db.close()

    def test_get_session_laps_returns_is_pit_lap(self):
        """get_session_laps must return is_pit_lap key."""
        db = self._make_db()
        sid = db.open_session(0, "Suzuka", "Practice")
        db.write_lap(sid, 1, 95_000, 3.5, self._make_stats(), is_pit_lap=True)
        laps = db.get_session_laps(sid)
        self.assertEqual(laps[0]["is_pit_lap"], 1)
        db.close()

    def test_fuel_start_end_round_trip(self):
        """fuel_start and fuel_end survive a write-then-read cycle."""
        db = self._make_db()
        sid = db.open_session(0, "Fuji", "Race")
        db.write_lap(sid, 3, 88_000, 2.9, self._make_stats(),
                     fuel_start=12.345, fuel_end=9.456)
        laps = db.get_session_laps(sid)
        self.assertAlmostEqual(laps[0]["fuel_start"], 12.345, places=3)
        self.assertAlmostEqual(laps[0]["fuel_end"],   9.456,  places=3)
        db.close()

    def test_fuel_start_end_default_zero(self):
        """Omitting fuel_start/fuel_end defaults to 0.0."""
        db = self._make_db()
        sid = db.open_session(0, "Suzuka", "Practice")
        db.write_lap(sid, 1, 90_000, 3.5, self._make_stats())
        laps = db.get_session_laps(sid)
        self.assertEqual(laps[0]["fuel_start"], 0.0)
        self.assertEqual(laps[0]["fuel_end"],   0.0)
        db.close()


# ---------------------------------------------------------------------------
# DEF-P1-007 — _computed_fuel_burn_lpl uses historical avg when session loaded
# ---------------------------------------------------------------------------

class TestFuelBurnSource(unittest.TestCase):

    def _make_fake_window(self):
        """Minimal fake MainWindow with the _computed_fuel_burn_lpl logic."""
        class FakeWindow:
            def __init__(self):
                self._tracker = None
                self._config = {"strategy": {"fuel_burn_per_lap": 2.0}}

            def _computed_fuel_burn_lpl(self) -> float:
                _loaded = getattr(self, "_loaded_session_avg_fuel", 0.0)
                if _loaded > 0:
                    return float(_loaded)
                if self._tracker and getattr(self._tracker, "avg_fuel_per_lap", 0) > 0:
                    return float(self._tracker.avg_fuel_per_lap)
                return float(self._config.get("strategy", {}).get("fuel_burn_per_lap", 2.0))

        return FakeWindow()

    def test_loaded_session_avg_fuel_takes_priority(self):
        """_loaded_session_avg_fuel is preferred over live tracker."""
        w = self._make_fake_window()
        w._loaded_session_avg_fuel = 4.2
        w._tracker = MagicMock()
        w._tracker.avg_fuel_per_lap = 3.0
        self.assertAlmostEqual(w._computed_fuel_burn_lpl(), 4.2, places=2)

    def test_live_tracker_used_when_no_loaded_session(self):
        """Live tracker avg used when no historical session is loaded."""
        w = self._make_fake_window()
        w._tracker = MagicMock()
        w._tracker.avg_fuel_per_lap = 3.0
        self.assertAlmostEqual(w._computed_fuel_burn_lpl(), 3.0, places=2)

    def test_config_fallback_when_neither_available(self):
        """Falls back to config fuel_burn_per_lap when tracker and loaded session absent."""
        w = self._make_fake_window()
        w._config["strategy"]["fuel_burn_per_lap"] = 2.5
        self.assertAlmostEqual(w._computed_fuel_burn_lpl(), 2.5, places=2)

    def test_live_lap_clears_loaded_avg(self):
        """Setting _loaded_session_avg_fuel = 0.0 (as _add_lap_row does) reverts to tracker."""
        w = self._make_fake_window()
        w._loaded_session_avg_fuel = 4.2
        w._tracker = MagicMock()
        w._tracker.avg_fuel_per_lap = 3.0
        # Simulate a live lap arriving
        w._loaded_session_avg_fuel = 0.0
        self.assertAlmostEqual(w._computed_fuel_burn_lpl(), 3.0, places=2)


# ---------------------------------------------------------------------------
# DEF-P1-006 — compound preference: DB value over stale _lap_compound_tags
# ---------------------------------------------------------------------------

class TestCompoundTagPreference(unittest.TestCase):

    def test_db_compound_preferred_over_stale_tag(self):
        """When DB supplies a non-empty compound, it must be used even if a stale
        tag exists in _lap_compound_tags for the same lap number."""
        # Reproduce the core logic extracted from _add_bank_lap_row
        def resolve_compound(compound: str, lap_num: int,
                              compound_tags: dict, default: str) -> str:
            if compound:
                return compound
            elif lap_num in compound_tags:
                return compound_tags[lap_num]
            else:
                prior_keys = [k for k in compound_tags if k < lap_num]
                return compound_tags[max(prior_keys)] if prior_keys else default

        stale_tags = {5: "RS"}  # stale tag from previous session
        result = resolve_compound("RM", 5, stale_tags, "")
        self.assertEqual(result, "RM", "DB compound 'RM' should override stale tag 'RS'")

    def test_empty_db_compound_falls_through_to_tag(self):
        """Empty DB compound falls through to existing tag."""
        def resolve_compound(compound, lap_num, compound_tags, default):
            if compound:
                return compound
            elif lap_num in compound_tags:
                return compound_tags[lap_num]
            else:
                prior_keys = [k for k in compound_tags if k < lap_num]
                return compound_tags[max(prior_keys)] if prior_keys else default

        tags = {4: "RH"}
        result = resolve_compound("", 5, tags, "")
        self.assertEqual(result, "RH")

    def test_get_session_laps_includes_compound(self):
        """get_session_laps must return the compound column."""
        from data.session_db import SessionDB
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = SessionDB(tmp.name)
        sid = db.open_session(0, "Suzuka", "Practice")
        stats = _make_stats()
        db.write_lap(sid, 1, 90_000, 3.5, stats, compound="RM")
        laps = db.get_session_laps(sid)
        self.assertEqual(laps[0]["compound"], "RM")
        db.close()


# ---------------------------------------------------------------------------
# DEF-P2-016 — validation gate logic
# ---------------------------------------------------------------------------

class TestValidationGateLogic(unittest.TestCase):
    """Test the validation rules that should block an AI call.

    The actual Qt dialog cannot be instantiated without a display, so we test
    the logic conditions in isolation.
    """

    def _should_block(self, race_type: str, total_laps: int, duration_mins: int,
                      fuel_burn: float, compound_lap_counts: dict) -> list[str]:
        """Reproduce the validation gate logic from _run_practice_analysis."""
        warnings = []
        if race_type == "timed" and duration_mins < 5:
            warnings.append("Race duration too short")
        elif race_type == "lap" and total_laps < 2:
            warnings.append("Race length too short")
        if fuel_burn <= 0:
            warnings.append("No fuel burn data")
        if not any(len(v) >= 2 for v in compound_lap_counts.values()):
            warnings.append("Need 2+ laps on one compound")
        return warnings

    def test_timed_race_1min_is_blocked(self):
        w = self._should_block("timed", 25, 1, 3.5, {"RM": [90_000.0, 91_000.0]})
        self.assertTrue(any("duration" in m.lower() for m in w))

    def test_timed_race_5min_passes_duration_check(self):
        w = self._should_block("timed", 25, 5, 3.5, {"RM": [90_000.0, 91_000.0]})
        self.assertFalse(any("duration" in m.lower() for m in w))

    def test_lap_race_1_lap_is_blocked(self):
        w = self._should_block("lap", 1, 0, 3.5, {"RM": [90_000.0, 91_000.0]})
        self.assertTrue(any("length" in m.lower() for m in w))

    def test_lap_race_25_laps_passes(self):
        w = self._should_block("lap", 25, 0, 3.5, {"RM": [90_000.0, 91_000.0]})
        self.assertEqual(w, [])

    def test_zero_fuel_burn_is_blocked(self):
        w = self._should_block("lap", 25, 0, 0.0, {"RM": [90_000.0, 91_000.0]})
        self.assertTrue(any("fuel" in m.lower() for m in w))

    def test_only_one_lap_per_compound_is_blocked(self):
        w = self._should_block("lap", 25, 0, 3.5, {"RM": [90_000.0], "RS": [88_000.0]})
        self.assertTrue(any("compound" in m.lower() or "2+" in m for m in w))

    def test_two_laps_on_one_compound_passes(self):
        w = self._should_block("lap", 25, 0, 3.5, {"RM": [90_000.0, 91_000.0]})
        self.assertEqual(w, [])

    def test_valid_data_produces_no_warnings(self):
        w = self._should_block("lap", 25, 0, 3.5, {"RM": [90_000.0, 91_000.0, 90_200.0]})
        self.assertEqual(w, [])

    def test_valid_timed_race_produces_no_warnings(self):
        w = self._should_block("timed", 0, 40, 3.5, {"RM": [90_000.0, 91_000.0]})
        self.assertEqual(w, [])

    def test_multiple_failures_all_reported(self):
        w = self._should_block("timed", 25, 1, 0.0, {"RM": [90_000.0]})
        self.assertGreaterEqual(len(w), 3)

# ---------------------------------------------------------------------------
# DEF-P2-012 — tyre wear multiplier source
# ---------------------------------------------------------------------------

class TestTyreWearSource(unittest.TestCase):

    def test_source_reads_tyre_wear_from_psc(self):
        """_run_practice_analysis must read tyre_wear_multiplier from the event config.

        AI Snapshot Migration: the read moved into the frozen snapshot layer
        (data/ai_context_snapshot.py) — verify the routing plus the value flow.
        """
        src = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("_build_practice_ai_snapshot", text,
                      "practice analysis must build race_params via the frozen snapshot")
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        rp = build_practice_analysis_snapshot(
            legacy_strategy={"track": "T", "tyre_wear_multiplier": 5.0},
            fuel_burn_override=2.5).race_params_dict()
        self.assertEqual(rp["tyre_wear_multiplier"], 5.0,
                         "strategy config must be the source for tyre_wear_multiplier")


if __name__ == "__main__":
    unittest.main()
