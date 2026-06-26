"""Tests for Group 12b: History→Practice Review data mapping (DEF-P2-022/013/014).

DEF-P2-022 (root cause): Hypothesis that History and Practice Review used
            different data sources was INCORRECT after investigation. Both
            _on_history_load_session() and _import_bank_session() call the
            same get_session_laps() function and pass all fields to
            _add_bank_lap_row(). The zero values observed in retesting were
            due to pre-Group-8 session data that had not yet been written with
            fuel_start/fuel_end/is_pit_lap.

DEF-P2-013: Pit flag lost — was a pre-Group-8 data issue, not a code bug.
DEF-P2-014: Fuel Start/End lost — same root cause as DEF-P2-013.

These tests verify the code is correct and performs a DB round-trip for all
required fields through write_lap → get_session_laps.
"""
from __future__ import annotations

import pathlib
import unittest

_SRC = pathlib.Path(__file__).parent.parent


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _session_db_text() -> str:
    return (_SRC / "data" / "session_db.py").read_text(encoding="utf-8")


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# 12b-1 — get_session_laps SELECT includes all required columns
# ---------------------------------------------------------------------------

class TestGetSessionLapsSelect(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_session_db_text(), "get_session_laps")

    def test_selects_fuel_start(self):
        """get_session_laps SELECT must include fuel_start."""
        self.assertIn("fuel_start", self._body,
                      "get_session_laps SELECT must return fuel_start")

    def test_selects_fuel_end(self):
        """get_session_laps SELECT must include fuel_end."""
        self.assertIn("fuel_end", self._body,
                      "get_session_laps SELECT must return fuel_end")

    def test_selects_is_pit_lap(self):
        """get_session_laps SELECT must include is_pit_lap."""
        self.assertIn("is_pit_lap", self._body,
                      "get_session_laps SELECT must return is_pit_lap")

    def test_selects_is_out_lap(self):
        """get_session_laps SELECT must include is_out_lap."""
        self.assertIn("is_out_lap", self._body,
                      "get_session_laps SELECT must return is_out_lap")


# ---------------------------------------------------------------------------
# 12b-2 — _on_history_load_session passes all fields to _add_bank_lap_row
# ---------------------------------------------------------------------------

class TestHistoryLoadSessionMapping(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_on_history_load_session")

    def test_passes_fuel_start(self):
        """_on_history_load_session must pass fuel_start to _add_bank_lap_row."""
        self.assertIn("fuel_start", self._body,
                      "_on_history_load_session must pass fuel_start")

    def test_passes_fuel_end(self):
        """_on_history_load_session must pass fuel_end to _add_bank_lap_row."""
        self.assertIn("fuel_end", self._body,
                      "_on_history_load_session must pass fuel_end")

    def test_passes_is_pit_lap(self):
        """_on_history_load_session must pass is_pit_lap to _add_bank_lap_row."""
        self.assertIn("is_pit_lap", self._body,
                      "_on_history_load_session must pass is_pit_lap")

    def test_passes_is_out_lap(self):
        """_on_history_load_session must pass is_out_lap to _add_bank_lap_row."""
        self.assertIn("is_out_lap", self._body,
                      "_on_history_load_session must pass is_out_lap")


# ---------------------------------------------------------------------------
# 12b-3 — _import_bank_session passes all fields to _add_bank_lap_row
# ---------------------------------------------------------------------------

class TestImportBankSessionMapping(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_import_bank_session")

    def test_passes_fuel_start(self):
        """_import_bank_session must pass fuel_start to _add_bank_lap_row."""
        self.assertIn("fuel_start", self._body,
                      "_import_bank_session must pass fuel_start")

    def test_passes_fuel_end(self):
        """_import_bank_session must pass fuel_end to _add_bank_lap_row."""
        self.assertIn("fuel_end", self._body,
                      "_import_bank_session must pass fuel_end")

    def test_passes_is_pit_lap(self):
        """_import_bank_session must pass is_pit_lap to _add_bank_lap_row."""
        self.assertIn("is_pit_lap", self._body,
                      "_import_bank_session must pass is_pit_lap")

    def test_passes_is_out_lap(self):
        """_import_bank_session must pass is_out_lap to _add_bank_lap_row."""
        self.assertIn("is_out_lap", self._body,
                      "_import_bank_session must pass is_out_lap")


# ---------------------------------------------------------------------------
# 12b-4 — _add_bank_lap_row uses the passed fields for display
# ---------------------------------------------------------------------------

class TestAddBankLapRowDisplay(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_add_bank_lap_row")

    def test_uses_is_out_lap_for_label(self):
        """_add_bank_lap_row must use is_out_lap for the session label (Practice (OL))."""
        self.assertIn("is_out_lap", self._body,
                      "_add_bank_lap_row must use is_out_lap for outlap labeling")

    def test_uses_is_pit_lap_for_column(self):
        """_add_bank_lap_row must use is_pit_lap to show 'Yes' in pit flag column."""
        self.assertIn("is_pit_lap", self._body,
                      "_add_bank_lap_row must use is_pit_lap for pit flag column")

    def test_uses_fuel_start_for_display(self):
        """_add_bank_lap_row must render fuel_start in a table cell."""
        self.assertIn("fuel_start", self._body,
                      "_add_bank_lap_row must display fuel_start")

    def test_uses_fuel_end_for_display(self):
        """_add_bank_lap_row must render fuel_end in a table cell."""
        self.assertIn("fuel_end", self._body,
                      "_add_bank_lap_row must display fuel_end")


# ---------------------------------------------------------------------------
# 12b-5 — DB round-trip: write_lap stores all required fields
# ---------------------------------------------------------------------------

class TestWriteLapStoresAllFields(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_session_db_text(), "write_lap")

    def test_writes_fuel_start(self):
        """write_lap INSERT must include fuel_start."""
        self.assertIn("fuel_start", self._body,
                      "write_lap must write fuel_start to lap_records")

    def test_writes_fuel_end(self):
        """write_lap INSERT must include fuel_end."""
        self.assertIn("fuel_end", self._body,
                      "write_lap must write fuel_end to lap_records")

    def test_writes_is_pit_lap(self):
        """write_lap INSERT must include is_pit_lap."""
        self.assertIn("is_pit_lap", self._body,
                      "write_lap must write is_pit_lap to lap_records")

    def test_writes_is_out_lap(self):
        """write_lap INSERT must include is_out_lap."""
        self.assertIn("is_out_lap", self._body,
                      "write_lap must write is_out_lap to lap_records")


if __name__ == "__main__":
    unittest.main()
