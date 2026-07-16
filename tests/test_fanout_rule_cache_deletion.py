"""Fan-Out Rule-Cache Deletion — the event-rule cache is gone, invisibly.

The final fan-out step (scoped by explicit product decision: "delete the rule
cache"). `_fanout_event_to_strategy` no longer writes the 12 event-RULE fields
(tyre wear, fuel mult, mandatory stops, weather, damage, refuel rate,
required/available tyres, mandatory_compounds, bop, tuning, allowed
categories) into `config["strategy"]` — every consumer reads the rules DB-first
through the canonical contexts (Phases 1–5 + Working Race Config), and
`config["events"]` covers the no-DB fallback. What remains is the legitimate
working-config core (track, race format/lengths, event_id) + plan state.

The INVISIBILITY proofs here are the sprint's evidence: for an active event,
every downstream surface produces identical output whether the strategy dict
carries fresh rules, stale rules, or no rules at all.

Also covered: the deletion of `_on_event_set_active`'s redundant writer-internal
permission call (Phase 3's sync already applies permissions from the just-saved
DB event) and the hardened driving-advisor fallback.
"""
from __future__ import annotations

import re
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data.event_context import build_event_context

ROOT = Path(__file__).resolve().parents[1]

RULE_FIELDS = ("tyre_wear_multiplier", "fuel_mult", "mandatory_stops",
               "weather", "damage", "refuel_speed_lps", "required_tyres",
               "mandatory_compounds", "avail_tyres", "bop", "tuning",
               "allowed_tuning_categories")


@pytest.fixture(scope="module")
def dash_src():
    # Event-list handlers (e.g. _on_event_set_active) moved to ui/event_planner_ui.py
    # in the dashboard decomposition; scan the combined source.
    return ((ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
            + (ROOT / "ui" / "event_planner_ui.py").read_text(encoding="utf-8"))


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


def _db_event():
    """A full DB event record (what upsert_event/_active_event provide)."""
    return {
        "id": 1, "name": "Race A", "track": "Spa",
        "race_type": "Lap Race", "laps": 12, "duration_mins": 0,
        "tyre_wear": 2, "fuel_mult": 3, "mandatory_stops": 1,
        "bop": True, "tuning": False, "weather": "Fixed Dry", "damage": "Light",
        "refuel_rate_lps": 5, "avail_tyres": ["RM", "RH"], "req_tyres": ["RM"],
        "allowed_tuning_categories": ["suspension"],
    }


def _core_only_strategy():
    """What the shrunk fan-out now leaves in config['strategy']."""
    return {"track": "Spa", "car": "Porsche 963", "config_id": "abc",
            "race_type": "lap", "laps": 12, "total_laps": 12,
            "race_duration_minutes": 0, "event_id": 1, "stops": []}


def _with_stale_rules():
    """A pre-deletion config: core + STALE rule-cache values (old activation)."""
    s = _core_only_strategy()
    s.update({"tyre_wear_multiplier": 9, "fuel_mult": 9, "mandatory_stops": 9,
              "weather": "Rain", "damage": "Heavy", "refuel_speed_lps": 1,
              "required_tyres": ["RS"], "mandatory_compounds": "Racing Soft",
              "avail_tyres": ["RS"], "bop": False, "tuning": True,
              "allowed_tuning_categories": ["aero"]})
    return s


# --------------------------------------------------------------------------- #
# 1. The shrunk fan-out helper (real method on a widget stub)
# --------------------------------------------------------------------------- #
def _make_fanout_stub():
    from ui import dashboard as _dash_mod
    stub = MagicMock()
    stub._config = {"strategy": {"car": "KeepMe", "config_id": "abc",
                                 "stops": [{"lap": 5}]}}
    stub._evt_track.currentText.return_value = "Spa"
    stub._evt_race_type.currentText.return_value = "Lap Race"
    stub._evt_laps.value.return_value = 12
    stub._evt_duration.value.return_value = 30
    stub._db = None
    stub._fanout_event_to_strategy = types.MethodType(
        _dash_mod.MainWindow._fanout_event_to_strategy, stub)
    return stub


class TestShrunkFanout:
    def test_writes_core_only(self):
        strat = _make_fanout_stub()._fanout_event_to_strategy("Race A")
        assert strat["track"] == "Spa"
        assert strat["race_type"] == "lap"
        assert strat["laps"] == 12 and strat["total_laps"] == 12
        assert strat["race_duration_minutes"] == 30
        assert strat["event_id"] == 0
        for gone in RULE_FIELDS:
            assert gone not in strat, f"rule-cache field {gone} written"

    def test_plan_state_still_never_touched(self):
        strat = _make_fanout_stub()._fanout_event_to_strategy("Race A")
        assert strat["car"] == "KeepMe"
        assert strat["config_id"] == "abc"
        assert strat["stops"] == [{"lap": 5}]

    def test_stale_rule_keys_left_alone_not_deleted(self):
        # Existing user configs keep their old keys (harmless, unread) — the
        # helper neither refreshes nor removes them.
        stub = _make_fanout_stub()
        stub._config["strategy"]["bop"] = True          # stale leftover
        strat = stub._fanout_event_to_strategy("Race A")
        assert strat["bop"] is True                      # untouched


# --------------------------------------------------------------------------- #
# 2. INVISIBILITY — downstream identical with fresh/stale/absent rule cache
# --------------------------------------------------------------------------- #
class TestInvisibilityProofs:
    def test_event_context_rules_identical_core_vs_stale_cache(self):
        # With a DB event present (DB-first per field), EventContext's rules
        # are identical whether the strategy dict carries stale rules or none.
        a = build_event_context(event=_db_event(), strategy=_core_only_strategy())
        b = build_event_context(event=_db_event(), strategy=_with_stale_rules())
        for field in ("tyre_wear_multiplier", "fuel_multiplier",
                      "mandatory_stops", "weather", "damage", "refuel_rate_lps",
                      "required_tyres", "available_tyres", "bop_enabled",
                      "tuning_allowed", "allowed_tuning_categories"):
            assert getattr(a, field) == getattr(b, field), field

    def test_event_context_rules_come_from_the_db_event(self):
        ctx = build_event_context(event=_db_event(), strategy=_core_only_strategy())
        assert ctx.tyre_wear_multiplier == 2.0
        assert ctx.fuel_multiplier == 3.0
        assert ctx.bop_enabled is True and ctx.tuning_allowed is False
        assert ctx.required_tyres == ("RM",)
        assert ctx.available_tyres == ("RM", "RH")
        assert ctx.weather == "Fixed Dry"

    def test_config_events_mirror_covers_the_no_db_fallback(self):
        # _active_event() falls back to the config["events"] mirror, which
        # carries the full rules — so even DB-less setups keep DB-first rules.
        mirror_event = _db_event()
        mirror_event.pop("id")            # the mirror entries have no DB id
        ctx = build_event_context(event=mirror_event,
                                  strategy=_core_only_strategy())
        assert ctx.bop_enabled is True
        assert ctx.tuning_allowed is False
        assert ctx.tyre_wear_multiplier == 2.0

    def test_ai_snapshot_contexts_source_ignores_the_legacy_rules(self):
        # The strategy AI snapshot's CONTEXTS source takes everything from the
        # canonical contexts; the legacy dict's rule keys (present or absent)
        # do not change the frozen race params.
        from data.analysis_inputs import build_strategy_inputs
        from data.strategy_context import build_strategy_context
        ev = build_event_context(event=_db_event(), strategy=_core_only_strategy())
        a = build_strategy_inputs(
            event_context=ev,
            strategy_context=build_strategy_context(strategy=_core_only_strategy()),
            legacy_strategy=_core_only_strategy())
        b = build_strategy_inputs(
            event_context=ev,
            strategy_context=build_strategy_context(strategy=_with_stale_rules()),
            legacy_strategy=_with_stale_rules())
        assert a.core.source.value == "contexts"
        assert a.race_params == b.race_params

    def test_working_race_config_unaffected(self):
        # The match-key inputs are core fields — untouched by the deletion.
        from data.working_race_config import WorkingRaceConfig
        a = WorkingRaceConfig.from_strategy(_core_only_strategy())
        b = WorkingRaceConfig.from_strategy(_with_stale_rules())
        assert a.compute_config_id() == b.compute_config_id()


# --------------------------------------------------------------------------- #
# 3. Source-scans — the deletion + the touch-ups
# --------------------------------------------------------------------------- #
class TestSourceScans:
    def test_helper_has_no_rule_writes(self, dash_src):
        body = _method_body(dash_src, "_fanout_event_to_strategy")
        for field in RULE_FIELDS:
            assert f'strat["{field}"]' not in body, f"{field} still written"
        for frag in ('strat["track"]', 'strat["race_type"]', 'strat["laps"]',
                     'strat["total_laps"]', 'strat["race_duration_minutes"]',
                     'strat["event_id"]'):
            assert frag in body

    def test_redundant_permission_call_deleted(self, dash_src):
        body = _method_body(dash_src, "_on_event_set_active")
        assert "self._apply_setup_permissions(" not in body, (
            "the writer-internal permission call was redundant (the sync "
            "applies permissions from the just-saved DB event) — deleted")
        assert "self._sync_setup_builder_from_event()" in body

    def test_advisor_fallback_hardened(self, dash_src):
        body = _method_body(dash_src, "_on_event_set_active")
        assert "_evt_full or self._active_event() or strat" in body

    def test_activation_side_effects_intact(self, dash_src):
        body = _method_body(dash_src, "_on_event_set_active")
        for frag in ("set_race_config", "_driving_advisor",
                     "_sync_strategy_from_event", "_persist_config",
                     "self._fanout_event_to_strategy(evt_name)"):
            assert frag in body


# --------------------------------------------------------------------------- #
# 4. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_frozen_allowlist_still_exact(self):
        from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
        assert _scan_inventory() == FROZEN_ALLOWLIST

    def test_golden_hash_vectors_still_green(self):
        # The deletion touches no hash input — spot-check a vector here too.
        from data.working_race_config import WorkingRaceConfig
        assert WorkingRaceConfig().compute_config_id() == "05e6d2f288"

    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
