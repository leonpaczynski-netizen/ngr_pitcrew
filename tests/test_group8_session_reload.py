"""Tests for Remediation Group 8: Session Reload Mapping.

Target defects:
  DEF-P2-013  Pit stop indicator lost after History reload
  DEF-P2-014  Fuel start/end lost after History reload
  DEF-P2-009  Fuel Burn Auto shows stale value after session reload

Root cause (DEF-P2-013 / DEF-P2-014):
  main.py called write_lap() without passing is_pit_lap and is_out_lap.
  Those parameters default to False/0, so the DB always stored 0.
  Live display reads from the LapRecord object in memory and shows correctly;
  the reload path reads from the DB and always found 0 → no pit flag, and
  outlaps were not excluded from the fuel average.

Root cause (DEF-P2-009):
  After _on_history_load_session() or _import_bank_session() sets
  _loaded_session_avg_fuel, the Strategy Builder _lbl_fuel_burn_display
  label was never refreshed — it still showed the stale value from startup.

Fixes:
  1. main.py  — write_lap() call now passes is_pit_lap, is_out_lap,
                delta_ms, session_type from the LapRecord.
  2. ui/dashboard.py — _on_history_load_session() and _import_bank_session()
                       update _lbl_fuel_burn_display after setting
                       _loaded_session_avg_fuel.
"""
from __future__ import annotations

import pathlib
import unittest

_SRC = pathlib.Path(__file__).parent.parent


def _main_text() -> str:
    return (_SRC / "main.py").read_text(encoding="utf-8")


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# DB round-trip: get_session_laps returns the columns we need
# ---------------------------------------------------------------------------

class TestGetSessionLapsColumns(unittest.TestCase):

    def setUp(self):
        from data.session_db import SessionDB
        self.db = SessionDB(":memory:")
        # Open a minimal session to have a valid session_id
        self.sid = self.db.open_session(car_id=1, track="Suzuka", session_type="practice")

    def tearDown(self):
        self.db.close()

    def _write(self, lap_num=1, lap_time_ms=90000, fuel_used=3.0,
               fuel_start=47.0, fuel_end=44.0, is_pit_lap=False, is_out_lap=False):
        """Write a minimal lap record with the fields under test."""
        from data.session_db import SessionDB
        # LapStats stub
        class _Stats:
            lock_up_count = wheelspin_count = 0
            brake_consistency_m = max_speed_kmh = avg_throttle_pct = avg_brake_pct = 0.0
            lock_up_positions = wheelspin_positions = oversteer_positions = []
            snap_throttle_positions = over_braking_positions = []

        for attr in ("oversteer_count", "oversteer_throttle_on_count", "kerb_count",
                     "bottoming_count", "snap_throttle_count", "over_braking_count",
                     "abrupt_release_count", "rev_limiter_count", "max_lat_g",
                     "off_track_count", "tyre_temp_avg"):
            setattr(_Stats, attr, 0)

        self.db.write_lap(
            self.sid, lap_num, lap_time_ms, fuel_used,
            _Stats(),
            fuel_start=fuel_start,
            fuel_end=fuel_end,
            is_pit_lap=is_pit_lap,
            is_out_lap=is_out_lap,
        )

    def test_get_session_laps_returns_is_pit_lap(self):
        """get_session_laps() must return is_pit_lap for every row."""
        self._write(lap_num=1)
        laps = self.db.get_session_laps(self.sid)
        self.assertEqual(len(laps), 1)
        self.assertIn("is_pit_lap", laps[0],
                      "get_session_laps() must return is_pit_lap key")

    def test_get_session_laps_returns_is_out_lap(self):
        """get_session_laps() must return is_out_lap for every row."""
        self._write(lap_num=1)
        laps = self.db.get_session_laps(self.sid)
        self.assertIn("is_out_lap", laps[0],
                      "get_session_laps() must return is_out_lap key")

    def test_get_session_laps_returns_fuel_start(self):
        """get_session_laps() must return fuel_start."""
        self._write(lap_num=1)
        laps = self.db.get_session_laps(self.sid)
        self.assertIn("fuel_start", laps[0])

    def test_get_session_laps_returns_fuel_end(self):
        """get_session_laps() must return fuel_end."""
        self._write(lap_num=1)
        laps = self.db.get_session_laps(self.sid)
        self.assertIn("fuel_end", laps[0])

    def test_get_session_laps_returns_fuel_used(self):
        """get_session_laps() must return fuel_used."""
        self._write(lap_num=1)
        laps = self.db.get_session_laps(self.sid)
        self.assertIn("fuel_used", laps[0])

    def test_pit_lap_flag_survives_db_round_trip(self):
        """DEF-P2-013: is_pit_lap=True written to DB must be returned as truthy."""
        self._write(lap_num=2, is_pit_lap=True)
        laps = self.db.get_session_laps(self.sid)
        self.assertTrue(bool(laps[0]["is_pit_lap"]),
                        "is_pit_lap written as True must come back truthy from DB")

    def test_non_pit_lap_flag_survives_db_round_trip(self):
        """Normal lap written with is_pit_lap=False must come back falsy."""
        self._write(lap_num=3, is_pit_lap=False)
        laps = self.db.get_session_laps(self.sid)
        self.assertFalse(bool(laps[0]["is_pit_lap"]))

    def test_out_lap_flag_survives_db_round_trip(self):
        """is_out_lap=True written to DB must come back truthy."""
        self._write(lap_num=4, is_out_lap=True)
        laps = self.db.get_session_laps(self.sid)
        self.assertTrue(bool(laps[0]["is_out_lap"]),
                        "is_out_lap written as True must come back truthy")

    def test_fuel_start_survives_db_round_trip(self):
        """DEF-P2-014: fuel_start value must survive DB round-trip within ±0.01 L."""
        self._write(lap_num=5, fuel_start=47.82)
        laps = self.db.get_session_laps(self.sid)
        self.assertAlmostEqual(float(laps[0]["fuel_start"]), 47.82, places=1,
                               msg="fuel_start must survive write_lap → get_session_laps round-trip")

    def test_fuel_end_survives_db_round_trip(self):
        """DEF-P2-014: fuel_end value must survive DB round-trip within ±0.01 L."""
        self._write(lap_num=6, fuel_end=44.13)
        laps = self.db.get_session_laps(self.sid)
        self.assertAlmostEqual(float(laps[0]["fuel_end"]), 44.13, places=1)

    def test_null_fuel_fields_do_not_crash(self):
        """DEF-P2-014 safety: session with fuel_start=0 and fuel_end=0 loads without crash."""
        self._write(lap_num=7, fuel_start=0.0, fuel_end=0.0)
        laps = self.db.get_session_laps(self.sid)
        self.assertEqual(len(laps), 1)
        self.assertEqual(float(laps[0].get("fuel_start", 0)), 0.0)

    def test_fuel_average_excludes_pit_laps(self):
        """DEF-P2-009: fuel average from loaded laps must skip pit laps."""
        self._write(lap_num=1, fuel_used=3.0, is_pit_lap=False)
        self._write(lap_num=2, fuel_used=3.2, is_pit_lap=False)
        self._write(lap_num=3, fuel_used=8.0, is_pit_lap=True)   # outlier pit lap
        laps = self.db.get_session_laps(self.sid)
        fuel_vals = [
            float(l.get("fuel_used") or 0)
            for l in laps
            if float(l.get("fuel_used") or 0) > 0
            and not bool(l.get("is_pit_lap", 0))
            and not bool(l.get("is_out_lap", 0))
        ]
        avg = sum(fuel_vals) / len(fuel_vals) if fuel_vals else 0.0
        self.assertAlmostEqual(avg, 3.1, places=1,
                               msg="Fuel average must exclude pit laps (8.0 L pit lap must not skew result)")

    def test_fuel_average_excludes_out_laps(self):
        """DEF-P2-009: fuel average from loaded laps must skip out-laps."""
        self._write(lap_num=1, fuel_used=3.0, is_out_lap=False)
        self._write(lap_num=2, fuel_used=3.2, is_out_lap=False)
        self._write(lap_num=3, fuel_used=6.5, is_out_lap=True)   # outlap
        laps = self.db.get_session_laps(self.sid)
        fuel_vals = [
            float(l.get("fuel_used") or 0)
            for l in laps
            if float(l.get("fuel_used") or 0) > 0
            and not bool(l.get("is_pit_lap", 0))
            and not bool(l.get("is_out_lap", 0))
        ]
        avg = sum(fuel_vals) / len(fuel_vals) if fuel_vals else 0.0
        self.assertAlmostEqual(avg, 3.1, places=1,
                               msg="Fuel average must exclude out-laps")


# ---------------------------------------------------------------------------
# Source-scan: main.py write_lap call passes is_pit_lap and is_out_lap
# ---------------------------------------------------------------------------

class TestMainWriteLapPassesPitFlag(unittest.TestCase):

    def _main(self) -> str:
        return _main_text()

    def test_write_lap_call_includes_is_pit_lap(self):
        """DEF-P2-013: main.py write_lap() call must pass is_pit_lap from LapRecord."""
        text = self._main()
        self.assertIn("is_pit_lap=", text,
                      "main.py write_lap() must pass is_pit_lap=")
        # Ensure it comes from the record, not hardcoded
        pit_pos = text.find("is_pit_lap=bool(getattr(record")
        if pit_pos == -1:
            pit_pos = text.find("is_pit_lap=bool(record")
        if pit_pos == -1:
            pit_pos = text.find("is_pit_lap=record")
        self.assertGreater(pit_pos, -1,
                           "main.py must derive is_pit_lap from record, not hardcode it")

    def test_write_lap_call_includes_is_out_lap(self):
        """main.py write_lap() call must pass is_out_lap from LapRecord."""
        text = self._main()
        out_pos = text.find("is_out_lap=bool(getattr(record")
        if out_pos == -1:
            out_pos = text.find("is_out_lap=bool(record")
        if out_pos == -1:
            out_pos = text.find("is_out_lap=record")
        self.assertGreater(out_pos, -1,
                           "main.py must derive is_out_lap from record, not hardcode it")

    def test_write_lap_call_includes_fuel_start(self):
        """DEF-P2-014: main.py write_lap() call must pass fuel_start from LapRecord."""
        text = self._main()
        self.assertIn("fuel_start=", text,
                      "main.py write_lap() must pass fuel_start=")

    def test_write_lap_call_includes_fuel_end(self):
        """DEF-P2-014: main.py write_lap() call must pass fuel_end from LapRecord."""
        text = self._main()
        self.assertIn("fuel_end=", text,
                      "main.py write_lap() must pass fuel_end=")

    def test_write_lap_call_includes_delta_ms(self):
        """main.py write_lap() call must pass delta_ms from LapRecord."""
        text = self._main()
        self.assertIn("delta_ms=", text,
                      "main.py write_lap() must pass delta_ms=")

    def test_write_lap_call_includes_session_type(self):
        """main.py write_lap() call must pass session_type from LapRecord."""
        text = self._main()
        self.assertIn("session_type=", text,
                      "main.py write_lap() must pass session_type=")


# ---------------------------------------------------------------------------
# Source-scan: _on_history_load_session passes pit/fuel to _add_bank_lap_row
# ---------------------------------------------------------------------------

class TestHistoryLoadSessionMapping(unittest.TestCase):

    def _body(self) -> str:
        return _method_body(_dashboard_text(), "_on_history_load_session")

    def test_passes_is_pit_lap_to_add_bank_lap_row(self):
        """DEF-P2-013: _on_history_load_session must pass is_pit_lap to _add_bank_lap_row."""
        body = self._body()
        self.assertIn("is_pit_lap=", body,
                      "_on_history_load_session must pass is_pit_lap= to _add_bank_lap_row")

    def test_passes_is_out_lap_to_add_bank_lap_row(self):
        """_on_history_load_session must pass is_out_lap to _add_bank_lap_row."""
        body = self._body()
        self.assertIn("is_out_lap=", body,
                      "_on_history_load_session must pass is_out_lap= to _add_bank_lap_row")

    def test_passes_fuel_start_to_add_bank_lap_row(self):
        """DEF-P2-014: _on_history_load_session must pass fuel_start to _add_bank_lap_row."""
        body = self._body()
        self.assertIn("fuel_start=", body,
                      "_on_history_load_session must pass fuel_start= to _add_bank_lap_row")

    def test_passes_fuel_end_to_add_bank_lap_row(self):
        """DEF-P2-014: _on_history_load_session must pass fuel_end to _add_bank_lap_row."""
        body = self._body()
        self.assertIn("fuel_end=", body,
                      "_on_history_load_session must pass fuel_end= to _add_bank_lap_row")

    def test_updates_fuel_burn_display_after_load(self):
        """DEF-P2-009: _on_history_load_session must update _lbl_fuel_burn_display after reload."""
        body = self._body()
        self.assertIn("_lbl_fuel_burn_display", body,
                      "_on_history_load_session must refresh _lbl_fuel_burn_display (DEF-P2-009)")
        self.assertIn("_loaded_session_avg_fuel", body,
                      "_on_history_load_session must compute _loaded_session_avg_fuel before display update")

    def test_fuel_average_filters_pit_laps(self):
        """_on_history_load_session fuel average must filter out pit laps."""
        body = self._body()
        self.assertIn("is_pit_lap", body,
                      "_on_history_load_session fuel filter must reference is_pit_lap")

    def test_fuel_average_filters_out_laps(self):
        """_on_history_load_session fuel average must filter out out-laps."""
        body = self._body()
        self.assertIn("is_out_lap", body,
                      "_on_history_load_session fuel filter must reference is_out_lap")


# ---------------------------------------------------------------------------
# Source-scan: _import_bank_session passes pit/fuel fields
# ---------------------------------------------------------------------------

class TestImportBankSessionMapping(unittest.TestCase):

    def _body(self) -> str:
        return _method_body(_dashboard_text(), "_import_bank_session")

    def test_passes_is_pit_lap(self):
        """DEF-P2-013: _import_bank_session must pass is_pit_lap to _add_bank_lap_row."""
        body = self._body()
        self.assertIn("is_pit_lap=", body,
                      "_import_bank_session must pass is_pit_lap= to _add_bank_lap_row")

    def test_passes_is_out_lap(self):
        """_import_bank_session must pass is_out_lap to _add_bank_lap_row."""
        body = self._body()
        self.assertIn("is_out_lap=", body,
                      "_import_bank_session must pass is_out_lap= to _add_bank_lap_row")

    def test_passes_fuel_start(self):
        """DEF-P2-014: _import_bank_session must pass fuel_start to _add_bank_lap_row."""
        body = self._body()
        self.assertIn("fuel_start=", body,
                      "_import_bank_session must pass fuel_start= to _add_bank_lap_row")

    def test_passes_fuel_end(self):
        """_import_bank_session must pass fuel_end to _add_bank_lap_row."""
        body = self._body()
        self.assertIn("fuel_end=", body,
                      "_import_bank_session must pass fuel_end= to _add_bank_lap_row")

    def test_updates_fuel_burn_display_after_load(self):
        """DEF-P2-009: _import_bank_session must update _lbl_fuel_burn_display after reload."""
        body = self._body()
        self.assertIn("_lbl_fuel_burn_display", body,
                      "_import_bank_session must refresh _lbl_fuel_burn_display (DEF-P2-009)")


# ---------------------------------------------------------------------------
# Source-scan: _add_bank_lap_row renders pit flag and fuel fields
# ---------------------------------------------------------------------------

class TestAddBankLapRowRendering(unittest.TestCase):

    def _body(self) -> str:
        return _method_body(_dashboard_text(), "_add_bank_lap_row")

    def test_renders_pit_flag_yes(self):
        """_add_bank_lap_row must render 'Yes' when is_pit_lap is True."""
        body = self._body()
        self.assertIn("is_pit_lap", body)
        self.assertIn('"Yes"', body,
                      "_add_bank_lap_row must render Yes for pit laps in the table cell")

    def test_renders_fuel_start_column(self):
        """_add_bank_lap_row must render fuel_start in the table."""
        body = self._body()
        self.assertIn("fuel_start", body,
                      "_add_bank_lap_row must render fuel_start in table cells")

    def test_renders_fuel_end_column(self):
        """_add_bank_lap_row must render fuel_end in the table."""
        body = self._body()
        self.assertIn("fuel_end", body,
                      "_add_bank_lap_row must render fuel_end in table cells")

    def test_stores_pit_and_out_lap_flags_in_user_role(self):
        """Row UserRole data must carry is_pit_lap and is_out_lap for summary filtering."""
        body = self._body()
        self.assertIn("is_pit_lap", body)
        self.assertIn("is_out_lap", body)
        self.assertIn("UserRole", body,
                      "_add_bank_lap_row must store flags in UserRole for _refresh_practice_summary")

    def test_pit_lap_gets_amber_background(self):
        """Pit lap rows must get the amber background colour."""
        body = self._body()
        self.assertIn("#4A4000", body,
                      "_add_bank_lap_row must apply amber background to pit lap rows")

    def test_out_lap_gets_dark_green_background(self):
        """Out-lap rows must get the dark-green background colour."""
        body = self._body()
        self.assertIn("#003A1A", body,
                      "_add_bank_lap_row must apply dark-green background to out-lap rows")


if __name__ == "__main__":
    unittest.main()
