"""Legacy Fan-Out Removal Phase 5 — functional readers + frozen allowlist guard.

Scope (explicit product decision: "Functional + guard"):

1. The remaining **functional** event-rule readers now use the canonical
   contexts (byte-identical in sync — and since Phase 4's re-sync, always in
   sync):
     * live-session open tagging (`_on_live_mode_changed`) — track/car/event_id
       from EventContext, config_id from StrategyContext;
     * degradation parameters — tyre wear (EventContext) + consecutive-lap
       window (StrategyContext);
     * BoP checks (`_get_bop_data_for_car` + the reload-BoP gate);
     * `_current_setup_dict` event-identity fields (car/track/weather/bop);
     * setup-save `event_id`.

2. A **frozen allowlist** pins every remaining `config["strategy"]` access site
   (file, enclosing method, count). Any NEW consumer — or any silent removal —
   fails this suite, forcing a conscious allowlist update.

Writer retirement remains deferred (docs/LEGACY_FANOUT_PHASE_5.md maps the
Phase 6 blockers: telemetry-path dispatcher reads, the config_id hash, restore
writers, plan-state persistence, context-builder bridges).
"""
from __future__ import annotations

import re
from collections import Counter
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


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


# --------------------------------------------------------------------------- #
# 1. The frozen allowlist — every remaining config["strategy"] access site
# --------------------------------------------------------------------------- #
# (file, enclosing function) -> number of access sites. Established by the
# Phase 5 audit (docs/LEGACY_FANOUT_PHASE_5.md classifies each). To migrate a
# reader: change the code AND shrink this list in the same commit. To add a
# consumer: don't — use the canonical contexts.
FROZEN_ALLOWLIST = {
    # -- ui/dashboard.py ---------------------------------------------------- #
    ("ui/dashboard.py", "__init__"): 1,                      # plan restore (stops)
    ("ui/dashboard.py", "_build_ai_analysis_group"): 2,      # fuel labels init
    ("ui/dashboard.py", "_build_event_context"): 1,          # bridge input
    ("ui/dashboard.py", "_build_practice_ai_snapshot"): 2,   # bridge input
    ("ui/dashboard.py", "_build_session_context"): 1,        # bridge input
    ("ui/dashboard.py", "_build_strategy_ai_snapshot"): 2,   # bridge input
    ("ui/dashboard.py", "_build_strategy_context"): 1,       # bridge input
    # Working Race Config sprint (2026-07-04): the hash + _update_race_config
    # display reads + strategy-sync no-event checks + session-save tagging now
    # read the named WorkingRaceConfig model; its builder is the single bridge
    # read for the concept.
    ("ui/dashboard.py", "_working_race_config"): 1,          # bridge (working config)
    ("ui/dashboard.py", "_display_practice_results"): 1,     # cosmetic
    ("ui/dashboard.py", "_fanout_event_to_strategy"): 1,     # THE writer
    ("ui/dashboard.py", "_live_init_from_plan"): 1,          # plan restore
    ("ui/dashboard.py", "_load_session_config"): 3,          # restore writer
    ("ui/dashboard.py", "_on_garage_select_for_event"): 1,   # car writer (garage)
    ("ui/dashboard.py", "_qual_use_practice_lap"): 1,        # cosmetic
    ("ui/dashboard.py", "_refresh_bop_label"): 1,            # cosmetic label
    ("ui/dashboard.py", "_resolve_setup_id_for_lap"): 1,     # cosmetic
    ("ui/dashboard.py", "_run_ai_analysis"): 1,              # plan state
    ("ui/dashboard.py", "_save_race_params"): 1,             # plan writer
    # (_save_session_to_db migrated to WorkingRaceConfig — entry removed)
    ("ui/dashboard.py", "_save_setup_from_lapdata"): 1,      # cosmetic
    ("ui/dashboard.py", "_sb_refresh_saved_plans_combo"): 1, # plan state
    ("ui/dashboard.py", "_sb_save_race_plan"): 1,            # plan state
    ("ui/dashboard.py", "_strategy_apply_plan"): 1,          # plan writer
    # (_sync_strategy_from_event residual migrated to WorkingRaceConfig — removed)
    ("ui/dashboard.py", "_update_race_config"): 1,           # config_id WRITER (read migrated)
    ("ui/dashboard.py", "_update_telemetry_labels"): 1,      # cosmetic
    ("ui/dashboard.py", "_worker"): 1,                       # degradation worker (plan)
    # -- ui/setup_builder_ui.py --------------------------------------------- #
    ("ui/setup_builder_ui.py", "_apply_and_save_ai_setup"): 1,   # cosmetic track (car read removed with the AI-Fix rename)
    ("ui/setup_builder_ui.py", "_apply_build_setup_result"): 1,  # cosmetic
    ("ui/setup_builder_ui.py", "_build_setup_ai_snapshot"): 2,   # bridge input
    ("ui/setup_builder_ui.py", "_build_setup_context"): 1,       # bridge input
    ("ui/setup_builder_ui.py", "_display_setup_result"): 3,      # history keys
    ("ui/setup_builder_ui.py", "_load_car_specs_for_current"): 1,  # car read
    ("ui/setup_builder_ui.py", "_open_car_ranges_dialog"): 1,    # cosmetic
    ("ui/setup_builder_ui.py", "_rebound_setup_spinboxes"): 1,   # car read
    ("ui/setup_builder_ui.py", "_set_dbl"): 2,                   # build-setup helper
    # -- ui/track_modelling_ui.py -------------------------------------------- #
    ("ui/track_modelling_ui.py", "_build_track_context"): 1,     # bridge input
    ("ui/track_modelling_ui.py", "_tm_on_layout_changed"): 2,    # THE combo writer
    # Group 62 UI: benign read-only restore of last-selected track (working-config core keys)
    ("ui/track_modelling_ui.py", "_tm_restore_last_track"): 1,   # read-only restore
    # -- main.py -------------------------------------------------------------- #
    # Phase 6a (2026-07-04): the two _dispatch telemetry-path reads are GONE —
    # the dispatcher now holds a frozen SessionTag pushed by the UI. One
    # construction-time seed read remains (before any thread starts).
    ("main.py", "__init__"): 1,                              # SessionTag seed — bridge
    # -- strategy/driving_advisor.py ----------------------------------------- #
    # Pre-existing legacy bridge reads, frozen 2026-07-04 when the scan was
    # extended to close the gap OFR-1's validator found.  After the I2 fix the
    # OFR-1 path contributes ZERO entries (_get_previous_ai_context retains
    # only its two pre-existing track reads; layout_id is now a literal "").
    ("strategy/driving_advisor.py", "build_coaching_response"): 1,
    ("strategy/driving_advisor.py", "build_combined_setup_response"): 1,
    ("strategy/driving_advisor.py", "build_driver_feeling_response"): 1,
    ("strategy/driving_advisor.py", "build_setup_advice_response"): 1,
    ("strategy/driving_advisor.py", "_build_combined_prompt"): 1,
    ("strategy/driving_advisor.py", "_build_setup_prompt"): 1,
    ("strategy/driving_advisor.py", "_car_track_header"): 1,
    ("strategy/driving_advisor.py", "_get_driver_feedback_context"): 1,
    ("strategy/driving_advisor.py", "_get_enriched_issue_context"): 1,
    ("strategy/driving_advisor.py", "_get_event_context_block"): 1,
    ("strategy/driving_advisor.py", "_get_history_context"): 1,
    ("strategy/driving_advisor.py", "_get_live_coaching_context"): 1,
    ("strategy/driving_advisor.py", "_get_live_segment_context"): 1,
    ("strategy/driving_advisor.py", "_get_previous_ai_context"): 2,
    ("strategy/driving_advisor.py", "_get_track_intelligence_context"): 1,
}

_SCAN_FILES = ("ui/dashboard.py", "ui/setup_builder_ui.py",
               "ui/track_modelling_ui.py", "main.py",
               "strategy/driving_advisor.py")
_ACCESS = re.compile(r'(?:get|setdefault)\("strategy"')


def _scan_inventory() -> dict:
    found = Counter()
    for rel in _SCAN_FILES:
        lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        defs = []
        for i, line in enumerate(lines, 1):
            m = re.match(r"(\s*)def (\w+)\(", line)
            if m:
                defs.append((i, m.group(2)))
        for i, line in enumerate(lines, 1):
            if _ACCESS.search(line) and not line.strip().startswith("#"):
                enclosing = "<module>"
                for dl, dn in defs:
                    if dl <= i:
                        enclosing = dn
                    else:
                        break
                found[(rel, enclosing)] += 1
    return dict(found)


class TestFrozenAllowlist:
    def test_no_new_or_removed_fanout_consumers(self):
        found = _scan_inventory()
        new = {k: v for k, v in found.items()
               if k not in FROZEN_ALLOWLIST or v > FROZEN_ALLOWLIST[k]}
        gone = {k: v for k, v in FROZEN_ALLOWLIST.items()
                if found.get(k, 0) < v}
        assert not new, (
            f"NEW config['strategy'] consumer(s) introduced: {new} — read the "
            "canonical contexts instead (see docs/LEGACY_FANOUT_PHASE_5.md)")
        assert not gone, (
            f"config['strategy'] site(s) removed without updating the frozen "
            f"allowlist: {gone} — shrink FROZEN_ALLOWLIST in the same commit")

    def test_allowlist_matches_exactly(self):
        assert _scan_inventory() == FROZEN_ALLOWLIST


# --------------------------------------------------------------------------- #
# 2. Byte-identity of the migrated functional reads (in-sync case)
# --------------------------------------------------------------------------- #
def _in_sync_pair():
    event = {"id": 7, "name": "Race A", "track": "Spa", "tyre_wear": 2,
             "bop": True, "weather": "Fixed Dry"}
    strategy = {"track": "Spa", "car": "Porsche 963", "event_id": 7,
                "config_id": "abc123", "tyre_wear_multiplier": 2,
                "bop": True, "weather": "Fixed Dry",
                "degradation_consecutive_laps": 2}
    return event, strategy


class TestByteIdentity:
    def test_session_tagging_fields(self):
        event, strategy = _in_sync_pair()
        ctx = build_event_context(event=event, strategy=strategy)
        sctx = build_strategy_context(strategy=strategy)
        # OLD (verbatim): strat.get("track"/"car"/"config_id", ""), int(strat.get("event_id", 0))
        assert ctx.track == strategy.get("track", "")
        assert ctx.car == strategy.get("car", "")
        assert sctx.config_id == strategy.get("config_id", "")
        assert int(ctx.event_id or 0) == int(strategy.get("event_id", 0))

    def test_session_tagging_empty_defaults(self):
        ctx = build_event_context()
        sctx = build_strategy_context()
        assert ctx.track == "" and ctx.car == ""
        assert sctx.config_id == ""
        assert int(ctx.event_id or 0) == 0

    def test_degradation_params(self):
        event, strategy = _in_sync_pair()
        ctx = build_event_context(event=event, strategy=strategy)
        sctx = build_strategy_context(strategy=strategy)
        assert float(ctx.tyre_wear_multiplier) == float(
            strategy.get("tyre_wear_multiplier", 1.0))
        assert int(sctx.degradation_consecutive_laps) == int(
            strategy.get("degradation_consecutive_laps", 2))
        # Defaults when nothing is set:
        assert float(build_event_context().tyre_wear_multiplier) == 1.0
        assert int(build_strategy_context().degradation_consecutive_laps) == 2

    def test_bop_gate_and_car(self):
        event, strategy = _in_sync_pair()
        ctx = build_event_context(event=event, strategy=strategy)
        assert ctx.bop_enabled == bool(strategy.get("bop", False))
        assert ctx.car == strategy.get("car", "")
        assert build_event_context().bop_enabled is False   # empty → gate closed

    def test_setup_dict_identity_fields(self):
        event, strategy = _in_sync_pair()
        ctx = build_event_context(event=event, strategy=strategy)
        # OLD: sc.get("car", "Unknown Car") or "Unknown Car"; sc.get("track","");
        # weather-map .get(sc.get("weather",""), "Dry"); bool(sc.get("bop", False))
        assert (ctx.car or "Unknown Car") == (
            strategy.get("car", "Unknown Car") or "Unknown Car")
        assert ctx.track == strategy.get("track", "")
        assert ctx.weather == strategy.get("weather", "")
        assert ctx.bop_enabled == bool(strategy.get("bop", False))
        # Empty state falls back exactly like the old read:
        empty = build_event_context()
        assert (empty.car or "Unknown Car") == "Unknown Car"


# --------------------------------------------------------------------------- #
# 3. Source-scans — the migrated methods read the contexts
# --------------------------------------------------------------------------- #
class TestMigratedConsumers:
    def test_live_mode_session_open(self, dash_src):
        body = _method_body(dash_src, "_on_live_mode_changed")
        assert "self._build_event_context()" in body
        assert "self._active_config_id()" in body
        assert "int(ev_ctx.event_id or 0)" in body
        assert 'config.get("strategy"' not in body

    def test_degradation_params(self, dash_src):
        assert ("wear_mult = float(self._build_event_context()"
                ".tyre_wear_multiplier)") in dash_src
        assert ("consecutive_laps = int(self._build_strategy_context()"
                ".degradation_consecutive_laps)") in dash_src

    def test_bop_data_for_car(self, dash_src):
        body = _method_body(dash_src, "_get_bop_data_for_car")
        assert "ev_ctx.bop_enabled" in body and "ev_ctx.car" in body
        assert 'config.get("strategy"' not in body

    def test_current_setup_dict(self, sbu_src):
        body = _method_body(sbu_src, "_current_setup_dict")
        assert "_ev_ctx = self._build_event_context()" in body
        assert "_ev_ctx.car or \"Unknown Car\"" in body
        assert "_ev_ctx.bop_enabled" in body
        assert 'config.get("strategy"' not in body

    def test_setup_save_event_id(self, sbu_src):
        assert "int(self._build_event_context().event_id or 0)" in sbu_src


# --------------------------------------------------------------------------- #
# 4. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_fanout_writer_and_resync_preserved(self, dash_src):
        helper = _method_body(dash_src, "_fanout_event_to_strategy")
        assert 'strat = self._config.setdefault("strategy", {})' in helper
        save = _method_body(dash_src, "_on_event_save")
        assert "self._fanout_event_to_strategy(name)" in save

    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
