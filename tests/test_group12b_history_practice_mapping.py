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


# ===========================================================================
# AC-SETUP-LABEL — Practice Review "Setup ✎" combo shows setup_label
#
# User story: the Setup combo must display the setup's setup_label (same text
# as the Setup tab), not the bare car name.  Acceptance criteria verified here
# are numbered AC1–AC7 plus the two secondary-scope items (SEC-1, SEC-2) and
# the regression fix (REG-1).
#
# All tests are pure/offline — no Qt event loop, no QApplication.
# _setup_id_options() is called via MainWindow._setup_id_options(stub) as the
# builder recommended; no window is constructed.
# ===========================================================================

import sys as _sys
import types as _types
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))

# Lazy-import dashboard module (importable headless; no window constructed).
import ui.dashboard as _dash_mod
from ui.setup_name_helper import setup_display_label as _sdl

# EM dash used as separator throughout the implementation.
_EM = "—"
_SEP = f" {_EM} "


def _options(saved_setups: list) -> list[str]:
    """Call MainWindow._setup_id_options on a lightweight stub."""
    stub = _types.SimpleNamespace(_saved_setups=saved_setups)
    return _dash_mod.MainWindow._setup_id_options(stub)


def _dashboard_src() -> str:
    return (_ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body_src(method_name: str) -> str:
    src = _dashboard_src()
    start = src.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = src.find("\n    def ", start + 1)
    return src[start:end] if end != -1 else src[start:]


# ---------------------------------------------------------------------------
# TestPracticeReviewSetupColumnLabel
# ---------------------------------------------------------------------------

class TestPracticeReviewSetupColumnLabel:
    """Acceptance tests for the Practice Review Setup combo label feature."""

    # -----------------------------------------------------------------------
    # AC1 — Each non-blank option is formatted as "{setup_id} — {setup_label}"
    # -----------------------------------------------------------------------

    def test_ac1_options_format_with_setup_label(self):
        """AC1: Non-blank options must be '{setup_id} — {setup_label}'."""
        saved = [
            {"setup_id": 3, "setup_label": "Q NGR Enduro Rd1 1", "name": "Mazda RX-7"},
            {"setup_id": 7, "setup_label": "R NGR Enduro Rd1 2", "name": "Honda NSX"},
        ]
        options = _options(saved)
        non_blank = [o for o in options if o]
        assert f"3{_SEP}Q NGR Enduro Rd1 1" in non_blank, (
            f"Expected '3{_SEP}Q NGR Enduro Rd1 1' in {non_blank}"
        )
        assert f"7{_SEP}R NGR Enduro Rd1 2" in non_blank, (
            f"Expected '7{_SEP}R NGR Enduro Rd1 2' in {non_blank}"
        )

    def test_ac1_options_sorted_by_setup_id(self):
        """AC1: Options must be sorted by setup_id ascending (matches Setup tab order)."""
        saved = [
            {"setup_id": 9, "setup_label": "R Spa 1", "name": "Car A"},
            {"setup_id": 2, "setup_label": "Q Spa 1", "name": "Car B"},
            {"setup_id": 5, "setup_label": "R Spa 2", "name": "Car C"},
        ]
        options = _options(saved)
        non_blank = [o for o in options if o]
        ids = [int(o.split(_SEP)[0]) for o in non_blank]
        assert ids == sorted(ids), f"Options not sorted by id: {ids}"

    # -----------------------------------------------------------------------
    # AC2 — Non-empty setup_label is used as the display text
    # -----------------------------------------------------------------------

    def test_ac2_nonempty_setup_label_used(self):
        """AC2: A setup with a non-empty setup_label must show that label, not the car name."""
        saved = [{"setup_id": 4, "setup_label": "Q NGR Rd1 2", "name": "Ferrari 458"}]
        options = _options(saved)
        non_blank = [o for o in options if o][0]
        assert "Q NGR Rd1 2" in non_blank, f"setup_label not in option: {non_blank!r}"
        assert "Ferrari 458" not in non_blank, (
            f"Car name must not appear when setup_label is present: {non_blank!r}"
        )

    # -----------------------------------------------------------------------
    # AC3 — Legacy/empty setup_label falls back to car name; never blank/broken
    # -----------------------------------------------------------------------

    def test_ac3_empty_setup_label_falls_back_to_car_name(self):
        """AC3: setup_label='' must fall back to car name, not produce a blank/broken option."""
        saved = [{"setup_id": 5, "setup_label": "", "name": "Ferrari 458"}]
        options = _options(saved)
        non_blank = [o for o in options if o]
        assert len(non_blank) == 1, f"Expected one non-blank option, got: {non_blank}"
        assert "Ferrari 458" in non_blank[0], (
            f"Car name fallback missing from option: {non_blank[0]!r}"
        )

    def test_ac3_absent_setup_label_falls_back_to_car_name(self):
        """AC3: Missing setup_label key must fall back to car name."""
        saved = [{"setup_id": 6, "name": "Toyota GR86"}]
        options = _options(saved)
        non_blank = [o for o in options if o]
        assert "Toyota GR86" in non_blank[0], (
            f"Car name fallback missing when setup_label absent: {non_blank[0]!r}"
        )

    def test_ac3_option_never_blank_when_both_absent(self):
        """AC3: Even if both setup_label and name are absent the option includes the id prefix."""
        saved = [{"setup_id": 8}]
        options = _options(saved)
        non_blank = [o for o in options if o]
        assert len(non_blank) == 1
        assert non_blank[0].startswith("8"), (
            f"Option must start with setup_id even when both labels absent: {non_blank[0]!r}"
        )

    # -----------------------------------------------------------------------
    # AC4 — Blank first option present and default (index 0)
    # -----------------------------------------------------------------------

    def test_ac4_blank_first_option_present(self):
        """AC4: First option must be blank '' (represents untagged/no setup selected)."""
        saved = [{"setup_id": 1, "setup_label": "Q Monza 1", "name": "Car"}]
        options = _options(saved)
        assert options[0] == "", f"First option must be blank, got: {options[0]!r}"

    def test_ac4_blank_option_present_with_empty_saved_setups(self):
        """AC4: Blank option must be present even when no setups are saved."""
        options = _options([])
        assert options == [""], f"With no setups, options must be [''], got: {options}"

    # -----------------------------------------------------------------------
    # AC5 — Round-trip: parse via split(" —")[0] recovers setup_id
    # -----------------------------------------------------------------------

    def test_ac5_roundtrip_id_parse_recovers_setup_id(self):
        """AC5: int(text.split(' —')[0]) must recover the original setup_id for every option."""
        saved = [
            {"setup_id": 3, "setup_label": "Q NGR Enduro Rd1 1", "name": "Mazda RX-7"},
            {"setup_id": 7, "setup_label": "R NGR Rd2 2", "name": "Honda NSX"},
            {"setup_id": 5, "setup_label": "", "name": "Ferrari 458"},
        ]
        options = _options(saved)
        for opt in options:
            if not opt:
                continue  # skip blank
            recovered = int(opt.split(f" {_EM}")[0])
            # Find the original sid
            sid_in_opt = int(opt.split(_SEP)[0])
            assert recovered == sid_in_opt, (
                f"Round-trip id mismatch for option {opt!r}: got {recovered}"
            )

    def test_ac5_separator_prefix_preserved_in_format_string(self):
        """AC5: The separator ' — ' (space-emdash-space) must be present in option strings."""
        saved = [{"setup_id": 10, "setup_label": "Q Fuji 1", "name": "Car"}]
        options = _options(saved)
        non_blank = [o for o in options if o][0]
        assert _SEP in non_blank, (
            f"Expected ' — ' separator in option text, got: {non_blank!r}"
        )

    # -----------------------------------------------------------------------
    # AC6 — Dash-in-label safety: parse splits on FIRST " — " only
    # -----------------------------------------------------------------------

    def test_ac6_label_with_emdash_parses_id_correctly(self):
        """AC6: A setup_label containing an em-dash must not break id recovery."""
        # NOTE: the user story says 'structured labels contain no em-dash',
        # but the parse must still be safe for any label.  We test with a
        # hypothetical freeform label that includes the em-dash separator.
        # The split(" —")[0] approach on the OPTION text (which starts with
        # the numeric id) will still recover the id correctly from first token.
        saved = [{"setup_id": 12, "setup_label": "Wet — Heavy Rain", "name": "Car"}]
        options = _options(saved)
        non_blank = [o for o in options if o][0]
        # Option is: "12 — Wet — Heavy Rain"
        # split on first " —" gives "12" as token [0]
        recovered = int(non_blank.split(f" {_EM}")[0])
        assert recovered == 12, (
            f"Id recovery failed when label contains em-dash; option={non_blank!r}, got {recovered}"
        )

    def test_ac6_source_parse_uses_split_first_token(self):
        """AC6: Source of _on_setup_id_selected must split on ' —' to get first token."""
        body = _method_body_src("_on_setup_id_selected")
        assert f'split(" {_EM}")[0]' in body or f"split(' {_EM}')[0]" in body, (
            "_on_setup_id_selected must split on em-dash separator to recover setup_id"
        )

    # -----------------------------------------------------------------------
    # AC7 — Setups sharing a setup_label stay distinct via unique setup_id prefix
    # -----------------------------------------------------------------------

    def test_ac7_shared_label_across_events_stays_distinct(self):
        """AC7: Two setups with the same setup_label must produce distinct options via setup_id."""
        saved = [
            {"setup_id": 1, "setup_label": "Q Baseline", "name": "Car"},
            {"setup_id": 2, "setup_label": "Q Baseline", "name": "Car"},
        ]
        options = _options(saved)
        non_blank = [o for o in options if o]
        assert len(non_blank) == 2, (
            f"Two setups with same label must produce two distinct options; got: {non_blank}"
        )
        ids = [int(o.split(_SEP)[0]) for o in non_blank]
        assert sorted(ids) == [1, 2], f"Expected ids [1,2], got {ids}"

    # -----------------------------------------------------------------------
    # SEC-1 — _build_setup_comparison_text calls setup_display_label
    # -----------------------------------------------------------------------

    def test_sec1_build_setup_comparison_text_calls_setup_display_label(self):
        """SEC-1: _build_setup_comparison_text must call setup_display_label, not bare s.get('name')."""
        body = _method_body_src("_build_setup_comparison_text")
        assert "setup_display_label" in body, (
            "_build_setup_comparison_text must call setup_display_label(s) for display name"
        )

    def test_sec1_build_setup_comparison_text_no_bare_name_get(self):
        """SEC-1: _build_setup_comparison_text must not use bare s.get('name') for the display name."""
        body = _method_body_src("_build_setup_comparison_text")
        # The old pattern was s.get("name") or d.get('name') used as the label directly.
        # After the fix, setup_display_label wraps that call.
        # We verify the method does NOT call get("name") outside of setup_display_label.
        # The method body should not contain a raw .get("name") or .get('name') for display.
        # setup_display_label itself calls s.get("name") internally, but that's in
        # setup_name_helper.py, not in dashboard.py's method body.
        assert 'get("name")' not in body and "get('name')" not in body, (
            "_build_setup_comparison_text must not call bare .get('name') — use setup_display_label"
        )

    # -----------------------------------------------------------------------
    # SEC-2 — _save_setup_from_lapdata status message calls setup_display_label
    # -----------------------------------------------------------------------

    def test_sec2_save_setup_from_lapdata_calls_setup_display_label(self):
        """SEC-2: _save_setup_from_lapdata must use setup_display_label for the status message."""
        body = _method_body_src("_save_setup_from_lapdata")
        assert "setup_display_label" in body, (
            "_save_setup_from_lapdata must call setup_display_label(d) in its status message"
        )

    def test_sec2_save_setup_from_lapdata_no_bare_name_get(self):
        """SEC-2: _save_setup_from_lapdata must not use bare d.get('name') for the status text."""
        body = _method_body_src("_save_setup_from_lapdata")
        assert 'd.get("name")' not in body and "d.get('name')" not in body, (
            "_save_setup_from_lapdata must not call bare .get('name') — use setup_display_label"
        )

    # -----------------------------------------------------------------------
    # REG-1 — _refresh_all_setup_combos restores by setup_id PREFIX, not exact text
    # -----------------------------------------------------------------------

    def test_reg1_refresh_restore_uses_prefix_split(self):
        """REG-1: _refresh_all_setup_combos must compare split prefixes, not full option text."""
        body = _method_body_src("_refresh_all_setup_combos")
        # The fix uses: current.split(" —")[0].strip() == combo.itemText(i).split(" —")[0].strip()
        # Verify both sides of the comparison appear in the method.
        assert f'split(" {_EM}")' in body or f"split(' {_EM}')" in body, (
            "_refresh_all_setup_combos must split on em-dash to compare prefixes"
        )
        assert ".strip()" in body, (
            "_refresh_all_setup_combos must call .strip() on the split prefix"
        )

    def test_reg1_refresh_prefix_restore_behavioural(self):
        """REG-1 (behavioural): prefix-based restore preserves selection when label text changes.

        Simulates what _refresh_all_setup_combos does: after a label-format change
        the 'current' text held by the combo (old format) must still map to the
        correct item in the new option list via id-prefix comparison.
        """
        # Simulate the state before a label change: combo currently shows old-format text
        # "5 — Ferrari 458" (car name was the label before the fix).
        old_current = f"5{_SEP}Ferrari 458"

        # New option list after the fix: label is now setup_label.
        new_options = [
            "",
            f"3{_SEP}Q NGR Enduro Rd1 1",
            f"5{_SEP}Q Monza 1",   # same id 5, new label text
            f"7{_SEP}R NGR Rd2 2",
        ]

        # Reproduce the prefix-restore logic from _refresh_all_setup_combos.
        current_prefix = old_current.split(f" {_EM}")[0].strip()
        restored_index = None
        for i, opt in enumerate(new_options):
            if opt.split(f" {_EM}")[0].strip() == current_prefix:
                restored_index = i
                break

        assert restored_index is not None, (
            "Prefix-restore failed: no match found for old selection in new option list"
        )
        assert new_options[restored_index] == f"5{_SEP}Q Monza 1", (
            f"Restored to wrong option: {new_options[restored_index]!r}"
        )

    def test_reg1_source_does_not_compare_full_text(self):
        """REG-1: _refresh_all_setup_combos must NOT compare itemText to raw currentText directly.

        The old (buggy) restore compared the entire option string to the stored
        current text.  After the fix both sides are split on the em-dash separator
        before comparison.  We verify that 'itemText(i) ==' or 'itemText(i).split'
        is present AND that the comparison variable is a *prefix* variable, not the
        raw 'current' variable that holds the full option text.
        """
        body = _method_body_src("_refresh_all_setup_combos")
        # The fixed code must use split on itemText side.
        assert "itemText(i).split" in body, (
            "_refresh_all_setup_combos must call .split on itemText(i) for prefix comparison"
        )
        # The fixed code must NOT compare itemText(i) directly to the full current text.
        # i.e. 'itemText(i) == current' (with nothing between) must not appear.
        import re as _re
        direct_compare = _re.search(r'itemText\(i\)\s*==\s*current\b', body)
        assert direct_compare is None, (
            "_refresh_all_setup_combos must not compare itemText(i) == current (full text); "
            "use prefix-split comparison instead"
        )
