"""Working Race Config Read Model sprint — retirement-map item 3 (readers).

`data/working_race_config.WorkingRaceConfig` names the concept Phase 6b
identified: the race configuration being worked on — usually the active event
(post-Phase-4, never silently drifted) but deliberately a restored historical
session's config during a lap-bank restore. It now owns the match-key algorithm
(`compute_config_id`) and is the read source for the migrated consumers:

  * `_compute_race_config_id` → delegates to the model (golden vectors in
    tests/test_race_config_id_hash.py still exercise the real dashboard method);
  * `_update_race_config` display line + race_configs snapshot values;
  * `_sync_strategy_from_event`'s no-event missing checks;
  * `_save_session_to_db`'s session tagging.

Writers keep their flows (the second half of item 3, with item 4).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from data.working_race_config import WorkingRaceConfig, WORKING_RACE_CONFIG_SCHEMA

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


# --------------------------------------------------------------------------- #
# 1. from_strategy — verbatim legacy reads
# --------------------------------------------------------------------------- #
class TestFromStrategy:
    def test_verbatim_reads(self):
        strat = {"track": "Spa", "car": "Porsche 963", "race_type": "timed",
                 "total_laps": 12, "race_duration_minutes": 30,
                 "config_id": "abc123"}
        wrc = WorkingRaceConfig.from_strategy(strat)
        assert wrc.track == strat.get("track", "")
        assert wrc.car == strat.get("car", "")
        assert wrc.race_type == strat.get("race_type", "lap")
        assert wrc.total_laps == int(strat.get("total_laps", 25))
        assert wrc.race_duration_minutes == int(strat.get("race_duration_minutes", 60))
        assert wrc.config_id == strat.get("config_id", "")

    def test_absent_key_defaults_are_the_hashs_own(self):
        # 25/60 — the hash's defaults, deliberately distinct from
        # EventContext's 0 defaults.
        wrc = WorkingRaceConfig.from_strategy({})
        assert wrc.track == "" and wrc.car == ""
        assert wrc.race_type == "lap"
        assert wrc.total_laps == 25
        assert wrc.race_duration_minutes == 60
        assert wrc.config_id == ""

    def test_none_strategy_safe(self):
        assert WorkingRaceConfig.from_strategy(None) == WorkingRaceConfig()

    def test_garbage_lengths_coerce_to_defaults(self):
        # Intentional hardening (documented): the old inline int() would raise
        # on non-numeric lengths; the model coerces to the field default.
        wrc = WorkingRaceConfig.from_strategy(
            {"total_laps": "abc", "race_duration_minutes": None})
        assert wrc.total_laps == 25
        assert wrc.race_duration_minutes == 60

    def test_immutable(self):
        with pytest.raises(Exception):
            WorkingRaceConfig().track = "X"


# --------------------------------------------------------------------------- #
# 2. The match-key algorithm (cross-checked with the golden-vector suite)
# --------------------------------------------------------------------------- #
class TestMatchKey:
    def test_length_key_and_raw(self):
        lap = WorkingRaceConfig(track="Spa", car="X", race_type="lap",
                                total_laps=12)
        assert lap.length_key == "l12"
        assert lap.hash_raw == "Spa|X|l12"
        timed = WorkingRaceConfig(track="Spa", car="X", race_type="timed",
                                  race_duration_minutes=30)
        assert timed.length_key == "t30"
        assert timed.is_timed is True

    def test_compute_config_id_matches_golden_vectors(self):
        # The same frozen vectors as tests/test_race_config_id_hash.py —
        # asserted directly on the model.
        assert WorkingRaceConfig().compute_config_id() == "05e6d2f288"
        assert WorkingRaceConfig(
            track="Spa", car="Porsche 963", race_type="lap", total_laps=12
        ).compute_config_id() == "51bd5b3bae"
        assert WorkingRaceConfig(
            track="Spa", car="Porsche 963", race_type="timed",
            race_duration_minutes=30
        ).compute_config_id() == "ab4f42df9a"

    def test_unknown_race_type_hashes_as_lap(self):
        weird = WorkingRaceConfig(track="T", car="C", race_type="endurance")
        lap = WorkingRaceConfig(track="T", car="C", race_type="lap")
        assert weird.compute_config_id() == lap.compute_config_id()

    def test_length_text_display(self):
        assert WorkingRaceConfig(race_type="lap", total_laps=12).length_text() == "12 laps"
        assert WorkingRaceConfig(race_type="timed",
                                 race_duration_minutes=30).length_text() == "30 min"

    def test_to_dict_schema(self):
        d = WorkingRaceConfig(track="Spa").to_dict()
        assert d["schema"] == WORKING_RACE_CONFIG_SCHEMA
        assert d["track"] == "Spa"

    def test_module_is_pure(self):
        src = (ROOT / "data" / "working_race_config.py").read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import PyQt6|from PyQt6)", src, re.M)
        assert "sqlite3" not in src


# --------------------------------------------------------------------------- #
# 3. Migrated consumers (source-scans)
# --------------------------------------------------------------------------- #
class TestMigratedConsumers:
    def test_builder_is_the_single_bridge(self, dash_src):
        body = _method_body(dash_src, "_working_race_config")
        assert 'WorkingRaceConfig.from_strategy(self._config.get("strategy", {}))' in body

    def test_hash_delegates(self, dash_src):
        body = _method_body(dash_src, "_compute_race_config_id")
        assert "self._working_race_config().compute_config_id()" in body
        assert 'config.get("strategy"' not in body

    def test_update_race_config_reads_the_model(self, dash_src):
        body = _method_body(dash_src, "_update_race_config")
        assert "wrc       = self._working_race_config()" in body
        assert "wrc.length_text()" in body
        # The read is gone; only the config_id WRITE (setdefault) remains.
        assert 'sc        = self._config.get("strategy", {})' not in body
        assert 'wsc = self._config.setdefault("strategy", {})' in body
        assert 'wsc["config_id"] = config_id' in body

    def test_snapshot_values_come_from_the_model(self, dash_src):
        body = _method_body(dash_src, "_update_race_config")
        # race_configs snapshot fields are the wrc-derived locals.
        for frag in ('"car":                   car',
                     '"track":                 track',
                     '"race_type":             race_type',
                     '"total_laps":            total_laps',
                     '"race_duration_minutes": race_duration'):
            assert frag in body

    def test_strategy_sync_missing_checks_use_model(self, dash_src):
        body = _method_body(dash_src, "_sync_strategy_from_event")
        assert "wrc = self._working_race_config()" in body
        assert "if not wrc.track:" in body
        assert "if not wrc.car:" in body
        assert 'sc.get("track")' not in body

    def test_session_save_tagging_uses_model(self, dash_src):
        body = _method_body(dash_src, "_save_session_to_db")
        assert "wrc       = self._working_race_config()" in body
        assert "config_id = wrc.config_id" in body
        assert 'strat.get("car"' not in body


# --------------------------------------------------------------------------- #
# 4. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_frozen_allowlist_matches_reshaped(self):
        from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
        assert _scan_inventory() == FROZEN_ALLOWLIST

    def test_writers_untouched(self, dash_src):
        # The second half of item 3 (writers) is deliberately deferred.
        helper = _method_body(dash_src, "_fanout_event_to_strategy")
        assert 'strat = self._config.setdefault("strategy", {})' in helper
        restore = _method_body(dash_src, "_load_session_config")
        assert 'setdefault("strategy", {})["track"]' in restore

    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
