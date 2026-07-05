"""
Group D — structured setup naming + local-time timestamp.

- Pure naming/numbering helpers (ui/setup_name_helper.py).
- Mixin _generate_setup_name behaviour (stubbed, no Qt).
- Source-scan guarantees: save guard, prefill wiring, old helper removed.
- setup_history timestamp is local time (no timezone.utc).
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.setup_name_helper import (
    build_setup_name,
    is_structured_name,
    next_setup_number,
    resolve_save_name,
    setup_display_label,
)
from ui import setup_builder_ui as _sbu_mod
import data.setup_history as _sh

SBU_SRC = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
SH_SRC = (ROOT / "data" / "setup_history.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
class TestNameHelpers:
    def test_build_name_qual(self):
        assert build_setup_name("Q", "NGR Enduro Rd1", 1) == "Q NGR Enduro Rd1 1"

    def test_build_name_race(self):
        assert build_setup_name("R", "NGR Enduro Rd1", 3) == "R NGR Enduro Rd1 3"

    def test_next_number_empty(self):
        assert next_setup_number([], "Q", "NGR Enduro Rd1") == 1

    def test_next_number_sequential(self):
        saved = [
            {"setup_label": "Q NGR Enduro Rd1 1"},
            {"setup_label": "Q NGR Enduro Rd1 2"},
        ]
        assert next_setup_number(saved, "Q", "NGR Enduro Rd1") == 3

    def test_next_number_gap_uses_max_plus_one(self):
        saved = [
            {"setup_label": "Q NGR Enduro Rd1 1"},
            {"setup_label": "Q NGR Enduro Rd1 3"},
        ]
        assert next_setup_number(saved, "Q", "NGR Enduro Rd1") == 4

    def test_prefix_does_not_cross_count(self):
        saved = [{"setup_label": "R NGR Enduro Rd1 1"}]  # race setup
        assert next_setup_number(saved, "Q", "NGR Enduro Rd1") == 1  # qualifying starts fresh

    def test_rd1_vs_rd10_no_bleed(self):
        saved = [
            {"setup_label": "Q NGR Enduro Rd1 1"},
            {"setup_label": "Q NGR Enduro Rd1 2"},
        ]
        assert next_setup_number(saved, "Q", "NGR Enduro Rd10") == 1

    def test_freeform_labels_ignored(self):
        saved = [
            {"setup_label": "Race Baseline"},
            {"setup_label": "My Fav"},
            {"setup_label": "Setup 1"},
        ]
        assert next_setup_number(saved, "Q", "NGR Enduro Rd1") == 1

    def test_special_chars_in_event_name(self):
        saved = [{"setup_label": "Q S.Croce+1 1"}]
        assert next_setup_number(saved, "Q", "S.Croce+1") == 2

    def test_blank_event_name_returns_one(self):
        assert next_setup_number([{"setup_label": "Q  1"}], "Q", "") == 1

    def test_non_dict_entries_skipped(self):
        assert next_setup_number([None, "x", {"setup_label": "Q E 1"}], "Q", "E") == 2


# ---------------------------------------------------------------------------
# D-RESAVE: resolve_save_name + is_structured_name
# ---------------------------------------------------------------------------
class TestResolveSaveName:
    def test_is_structured_name_matches_either_prefix(self):
        assert is_structured_name("Q NGR Rd1 2", "NGR Rd1") is True
        assert is_structured_name("R NGR Rd1 10", "NGR Rd1") is True

    def test_is_structured_name_rejects_freeform(self):
        assert is_structured_name("Race Baseline", "NGR Rd1") is False
        assert is_structured_name("Q NGR Rd1 abc", "NGR Rd1") is False
        assert is_structured_name("Q NGR Rd10 1", "NGR Rd1") is False  # wrong event

    def test_empty_field_resolves_to_first_number(self):
        assert resolve_save_name("", "Q", "NGR Rd1", []) == "Q NGR Rd1 1"

    def test_loaded_structured_name_advances_to_next(self):
        # D-RESAVE: load "Q NGR Rd1 2", save -> "Q NGR Rd1 3" (not an overwrite).
        saved = [{"setup_label": "Q NGR Rd1 1"}, {"setup_label": "Q NGR Rd1 2"}]
        assert resolve_save_name("Q NGR Rd1 2", "Q", "NGR Rd1", saved) == "Q NGR Rd1 3"

    def test_manual_freeform_name_preserved(self):
        assert resolve_save_name("My Wet Setup", "Q", "NGR Rd1", []) == "My Wet Setup"

    def test_consecutive_saves_increment(self):
        saved = []
        n1 = resolve_save_name("", "R", "E", saved)
        assert n1 == "R E 1"
        saved.append({"setup_label": n1})
        n2 = resolve_save_name(n1, "R", "E", saved)  # field still shows n1
        assert n2 == "R E 2"


# ---------------------------------------------------------------------------
# Mixin _generate_setup_name / prefix (stubbed, no Qt)
# ---------------------------------------------------------------------------
class TestGenerateSetupName:
    def _make_stub(self, *, type_text="Qualifying Setup", event=None, saved=None):
        stub = MagicMock()
        stub._setup_type.currentText.return_value = type_text
        stub._active_event.return_value = event if event is not None else {}
        stub._saved_setups = saved if saved is not None else []
        stub._setup_type_prefix = types.MethodType(
            _sbu_mod.SetupBuilderMixin._setup_type_prefix, stub
        )
        stub._generate_setup_name = types.MethodType(
            _sbu_mod.SetupBuilderMixin._generate_setup_name, stub
        )
        return stub

    def test_prefix_qual(self):
        stub = self._make_stub(type_text="Qualifying Setup")
        assert stub._setup_type_prefix() == "Q"

    def test_prefix_race(self):
        stub = self._make_stub(type_text="Race Setup")
        assert stub._setup_type_prefix() == "R"

    def test_generate_returns_none_without_event(self):
        stub = self._make_stub(event={})
        assert stub._generate_setup_name() is None

    def test_generate_returns_structured_name(self):
        stub = self._make_stub(type_text="Qualifying Setup", event={"name": "NGR Rd1"}, saved=[])
        assert stub._generate_setup_name() == "Q NGR Rd1 1"

    def test_generate_increments_with_existing(self):
        stub = self._make_stub(
            type_text="Race Setup",
            event={"name": "NGR Rd1"},
            saved=[{"setup_label": "R NGR Rd1 1"}],
        )
        assert stub._generate_setup_name() == "R NGR Rd1 2"


# ---------------------------------------------------------------------------
# Source-scan structural guarantees
# ---------------------------------------------------------------------------
class TestStructural:
    def test_old_suggest_helper_removed(self):
        assert "_suggest_setup_label" not in SBU_SRC

    def test_generate_and_prefill_methods_exist(self):
        assert "def _generate_setup_name" in SBU_SRC
        assert "def _prefill_setup_label" in SBU_SRC

    def test_save_guard_requires_active_event(self):
        # _setup_save must abort with a message when there is no active event.
        assert "No Active Event" in SBU_SRC
        assert "_active_event" in SBU_SRC

    def test_prefill_wired_on_type_and_event_change(self):
        # Both wiring points call the prefill.
        assert SBU_SRC.count("self._prefill_setup_label()") >= 2

    def test_timestamp_uses_local_not_utc(self):
        assert "datetime.now(timezone.utc)" not in SH_SRC
        assert "datetime.now()" in SH_SRC

    def test_timezone_import_removed(self):
        assert "timezone" not in SH_SRC


# ---------------------------------------------------------------------------
# setup_history timestamp is local time
# ---------------------------------------------------------------------------
class TestLocalTimestamp:
    def test_save_entry_writes_local_time(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_sh, "_HISTORY_PATH", tmp_path / "hist.json")
        fixed = _dt.datetime(2026, 6, 29, 14, 30, 5)

        class _FakeDT:
            @classmethod
            def now(cls, tz=None):
                assert tz is None, "setup timestamp must use local time, not an explicit tz"
                return fixed

        monkeypatch.setattr(_sh, "datetime", _FakeDT)
        _sh.save_entry("cfgX", "Car", "Track", {"type": "build_race"})

        data = json.loads((tmp_path / "hist.json").read_text(encoding="utf-8"))
        ts = data["cfgX"]["entries"][0]["ts"]
        assert ts == "2026-06-29T14:30:05"


class TestSetupDisplayLabel:
    """UAT: setup names in Practice Review must match the saved setup_label,
    not the car name (which is what the legacy ``name`` field holds)."""

    def test_prefers_setup_label(self):
        s = {"name": "Porsche 911 RSR", "setup_label": "R NGR Porsche Cup Rd7 2"}
        assert setup_display_label(s) == "R NGR Porsche Cup Rd7 2"

    def test_falls_back_to_name_when_no_label(self):
        assert setup_display_label({"name": "Mazda 787B"}) == "Mazda 787B"

    def test_empty_label_falls_back_to_name(self):
        s = {"name": "Mazda 787B", "setup_label": ""}
        assert setup_display_label(s) == "Mazda 787B"

    def test_empty_dict_returns_blank(self):
        assert setup_display_label({}) == ""

    def test_non_dict_returns_blank(self):
        assert setup_display_label(None) == ""

    def test_strips_whitespace(self):
        assert setup_display_label({"setup_label": "  Q Fuji 1  "}) == "Q Fuji 1"
