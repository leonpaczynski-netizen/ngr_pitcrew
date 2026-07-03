"""Legacy Fan-Out Removal Phase 1 — read-only consumer migration.

This sprint migrates a focused set of **low-risk, read-only** config["strategy"]
consumers to the canonical read models, proving each is byte-identical:

  * config_id (strategy-plan identity) → StrategyContext.config_id
      - ui/setup_builder_ui.py: _display_setup_result, _run_build_setup (history
        save keys), _refresh_setup_history_combo, _on_setup_history_selected
        (read-only history lookups) — via the new MainWindow._active_config_id().
  * car (event selection) → EventContext.car
      - ui/dashboard.py: _sync_practice_from_event (practice-bank combo sync).

The fan-out WRITERS are deliberately preserved:
  * Event Planner "Set as Active" (_on_event_set_active) fans event/race fields
    into config["strategy"].
  * Track Modelling combo selection writes track_location_id/layout_id.

Pure-Python byte-identity tests + source-scans (the project's no-Qt convention).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from data.event_context import build_event_context
from data.strategy_context import build_strategy_context

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sbu_src():
    return (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tm_src():
    return (ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


# --------------------------------------------------------------------------- #
# 1. Byte-identity: the migrated reads equal the legacy expressions
# --------------------------------------------------------------------------- #
class TestConfigIdByteIdentical:
    """StrategyContext.config_id == config['strategy'].get('config_id', '')."""

    @pytest.mark.parametrize("strategy", [
        {},
        {"config_id": ""},
        {"config_id": "0a1b2c3d4e"},
        {"config_id": "abc123", "car": "X", "track": "Y", "stops": []},
        {"track": "Suzuka"},  # config_id absent
    ])
    def test_matches_legacy_read(self, strategy):
        legacy = strategy.get("config_id", "")
        ctx = build_strategy_context(strategy=strategy)
        assert ctx.config_id == legacy

    def test_absent_and_empty_both_empty_string(self):
        assert build_strategy_context(strategy={}).config_id == ""
        assert build_strategy_context(strategy={"config_id": ""}).config_id == ""


class TestCarByteIdentical:
    """EventContext.car == config['strategy'].get('car', '') (car is resolved
    strategy-first in EventContext, and the events table never stores a car)."""

    @pytest.mark.parametrize("strategy", [
        {},
        {"car": ""},
        {"car": "Toyota GR010 HYBRID"},
        {"car": "Mazda 787B", "track": "Spa"},
    ])
    def test_matches_legacy_read_strategy_only(self, strategy):
        legacy = strategy.get("car", "")
        ctx = build_event_context(strategy=strategy)
        assert ctx.car == legacy

    def test_car_unaffected_by_db_event_without_car(self):
        # A DB event record (which never carries a car) must not change the car.
        strategy = {"car": "Porsche 963"}
        event = {"id": 5, "name": "Race", "track": "Le Mans"}  # no 'car' key
        ctx = build_event_context(event=event, strategy=strategy)
        assert ctx.car == "Porsche 963"


# --------------------------------------------------------------------------- #
# 2. The migrated consumers now read from the canonical contexts
# --------------------------------------------------------------------------- #
class TestMigratedConsumers:
    def test_active_config_id_helper_exists_and_uses_strategy_context(self, dash_src):
        body = _method_body(dash_src, "_active_config_id")
        assert "_build_strategy_context()" in body
        assert ".config_id" in body

    def test_setup_builder_has_no_raw_config_id_reads(self, sbu_src):
        assert 'get("config_id"' not in sbu_src, (
            "setup_builder still reads config_id from raw config['strategy']")
        # All four sites now go through the helper.
        assert sbu_src.count("self._active_config_id()") == 4

    def test_history_lookups_use_helper(self, sbu_src):
        for name in ("_refresh_setup_history_combo", "_on_setup_history_selected"):
            body = _method_body(sbu_src, name)
            assert "self._active_config_id()" in body, f"{name} not migrated"
            assert 'config.get("strategy"' not in body, (
                f"{name} still reads config['strategy'] directly")

    def test_practice_sync_reads_car_from_event_context(self, dash_src):
        body = _method_body(dash_src, "_sync_practice_from_event")
        assert "self._build_event_context().car" in body
        assert 'self._config.get("strategy", {}).get("car"' not in body, (
            "_sync_practice_from_event still reads the car from config['strategy']")


# --------------------------------------------------------------------------- #
# 3. The fan-out WRITERS are preserved (out of scope this sprint)
# --------------------------------------------------------------------------- #
class TestWritersPreserved:
    def test_event_planner_set_active_writer_intact(self, dash_src):
        body = _method_body(dash_src, "_on_event_set_active")
        # The fan-out still writes event/race fields into config["strategy"].
        assert 'strat = self._config.setdefault("strategy", {})' in body
        for frag in ('strat["track"]', 'strat["bop"]', 'strat["tuning"]',
                     'strat["event_id"]'):
            assert frag in body, f"Set-as-Active fan-out lost {frag}"

    def test_track_modelling_combo_writer_intact(self, tm_src):
        assert 'setdefault("strategy", {})["track_location_id"]' in tm_src
        assert 'setdefault("strategy", {})["layout_id"]' in tm_src

    def test_config_strategy_not_removed(self, dash_src):
        # Legacy compatibility cache must still exist.
        assert 'self._config.get("strategy"' in dash_src


# --------------------------------------------------------------------------- #
# 4. No NEW fan-out introduced by the migration
# --------------------------------------------------------------------------- #
class TestNoNewFanout:
    def test_migrated_methods_do_not_write_config_strategy(self, dash_src, sbu_src):
        for src, name in ((dash_src, "_active_config_id"),
                          (dash_src, "_sync_practice_from_event"),
                          (sbu_src, "_refresh_setup_history_combo"),
                          (sbu_src, "_on_setup_history_selected")):
            body = _method_body(src, name)
            assert 'setdefault("strategy"' not in body, f"{name} writes config['strategy']"
            assert re.search(r'\[.strategy.\]\s*\[', body) is None, (
                f"{name} writes into config['strategy']")

    def test_only_the_two_known_writers_exist(self, dash_src, sbu_src, tm_src):
        # setdefault("strategy", ...) sites: several in dashboard belong to the
        # existing writers/restore paths (out of scope); NONE were added here and
        # setup_builder introduces no writer at all.
        assert 'setdefault("strategy"' not in sbu_src, (
            "setup_builder must not write config['strategy']")
        # Track Modelling's only strategy writes are the two combo-id fan-outs.
        tm_writes = re.findall(r'setdefault\(.strategy.,\s*\{\}\)\["(\w+)"\]', tm_src)
        assert set(tm_writes) == {"track_location_id", "layout_id"}, tm_writes


# --------------------------------------------------------------------------- #
# 5. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
