"""Legacy Fan-Out Removal Phase 2 — event-rule DISPLAY-label migration.

Scope (chosen: "display labels only"): the event-context READOUT labels on the
Strategy and Setup tabs now reflect the canonical **EventContext** (DB-event-
first — consistent with what the strategy/setup AI already consumes since the AI
Snapshot Migration). The FUNCTIONAL paths — setup-permission gating
(`_apply_setup_permissions`), the BoP toggle (`_on_bop_toggled`), and the spinbox
rebind — deliberately still read the active `config["strategy"]` fan-out, so
Phase 2 changes no functional behaviour (which fields are editable is unchanged).

Two guarantees, both tested here:
  1. **Byte-identical when in sync** — when the DB event and the config fan-out
     agree (the normal case, right after "Set as Active"), every migrated label
     value equals the old strategy-first raw read. Integer QSpinBox values are
     wrapped in int() so "2×" stays "2×" (not "2.0×").
  2. **DB-first when diverged** — after an event is edited + Saved but not
     re-activated (DB fresh, fan-out stale), the labels show the DB truth (the
     intended behaviour change; matches the AI inputs).

Pure-Python EventContext equivalence tests + source-scans (no-Qt convention).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from data.event_context import build_event_context

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


# A realistic in-sync pair: a DB event record (DB field names) and the
# config["strategy"] fan-out (config field names) that "Set as Active" produces
# from it — same integer QSpinBox values on both sides.
def _in_sync_pair():
    event = {
        "id": 1, "name": "Race A", "track": "Spa",
        "race_type": "Timed Race",          # DB stores the combo display text
        "duration_mins": 30, "laps": 12,
        "tyre_wear": 2, "fuel_mult": 3, "mandatory_stops": 1,
        "bop": True, "tuning": False,
        "weather": "Fixed Dry", "damage": "Light",
        "avail_tyres": ["RH", "RM"], "req_tyres": ["RM"],
        "allowed_tuning_categories": ["suspension"], "refuel_rate_lps": 5,
    }
    strategy = {
        "track": "Spa", "car": "Porsche 963",
        "race_type": "timed",               # config stores the normalised token
        "race_duration_minutes": 30, "total_laps": 12,
        "tyre_wear_multiplier": 2, "fuel_mult": 3, "mandatory_stops": 1,
        "bop": True, "tuning": False,
        "weather": "Fixed Dry", "damage": "Light",
        "avail_tyres": ["RH", "RM"], "required_tyres": ["RM"],
        "allowed_tuning_categories": ["suspension"], "refuel_speed_lps": 5,
    }
    return event, strategy


# --------------------------------------------------------------------------- #
# 1. Byte-identical label VALUES when the DB event and the fan-out agree
# --------------------------------------------------------------------------- #
class TestInSyncByteIdentical:
    def test_numeric_labels_match_int_of_raw(self):
        event, strategy = _in_sync_pair()
        ctx = build_event_context(event=event, strategy=strategy)
        # Setup/strategy labels use int() on integer QSpinBox values.
        assert int(ctx.tyre_wear_multiplier) == strategy["tyre_wear_multiplier"]
        assert int(ctx.fuel_multiplier) == strategy["fuel_mult"]
        assert int(ctx.refuel_rate_lps) == strategy["refuel_speed_lps"]
        assert ctx.mandatory_stops == int(strategy["mandatory_stops"])
        assert int(ctx.race_duration_minutes) == strategy["race_duration_minutes"]
        assert ctx.laps == strategy["total_laps"]

    def test_string_and_bool_labels_match_raw(self):
        event, strategy = _in_sync_pair()
        ctx = build_event_context(event=event, strategy=strategy)
        assert ctx.track == strategy["track"]
        assert ctx.car == strategy["car"]
        assert ctx.weather == strategy["weather"]
        assert ctx.damage == strategy["damage"]
        assert ctx.bop_enabled == bool(strategy["bop"])
        assert ctx.tuning_allowed == bool(strategy["tuning"])
        # race_type: DB stores "Timed Race", config "timed" — both normalise to
        # "timed", so the "Timed Race"/"Lap Race" label is byte-identical.
        assert ctx.race_type == strategy["race_type"] == "timed"

    def test_integer_formatting_preserved_not_floated(self):
        # The reason int() matters: raw "2×" must not become "2.0×".
        event, strategy = _in_sync_pair()
        ctx = build_event_context(event=event, strategy=strategy)
        assert f"×{int(ctx.tyre_wear_multiplier)}" == "×2"
        assert f"×{int(ctx.fuel_multiplier)}" == "×3"
        assert f"{int(ctx.refuel_rate_lps)} L/s" == "5 L/s"


# --------------------------------------------------------------------------- #
# 2. DB-first when the fan-out is stale (the intended behaviour change)
# --------------------------------------------------------------------------- #
class TestDivergedDbFirst:
    def test_edited_event_not_reactivated_shows_db_truth(self):
        # Event edited+Saved (DB fresh) but not re-activated (fan-out stale).
        event, strategy = _in_sync_pair()
        event.update({"tyre_wear": 5, "fuel_mult": 4, "bop": False,
                      "tuning": True, "weather": "Rain", "duration_mins": 45})
        # strategy (fan-out) still holds the OLD values from the last activation.
        ctx = build_event_context(event=event, strategy=strategy)
        assert int(ctx.tyre_wear_multiplier) == 5        # was 2 in the fan-out
        assert int(ctx.fuel_multiplier) == 4             # was 3
        assert ctx.bop_enabled is False                  # was True
        assert ctx.tuning_allowed is True                # was False
        assert ctx.weather == "Rain"                     # was Fixed Dry
        assert int(ctx.race_duration_minutes) == 45      # was 30

    def test_car_and_track_id_stay_strategy_sourced(self):
        # car / track ids are not stored on the DB event, so they remain
        # strategy-sourced even under DB-first resolution.
        event, strategy = _in_sync_pair()
        ctx = build_event_context(event=event, strategy=strategy)
        assert ctx.car == "Porsche 963"


# --------------------------------------------------------------------------- #
# 3. Only DISPLAY labels moved — functional paths still read config["strategy"]
# --------------------------------------------------------------------------- #
class TestSetupSyncMigration:
    def test_builds_event_context(self, sbu_src):
        body = _method_body(sbu_src, "_sync_setup_builder_from_event")
        assert "ev_ctx = self._build_event_context()" in body

    def test_display_labels_read_event_context(self, sbu_src):
        body = _method_body(sbu_src, "_sync_setup_builder_from_event")
        for frag in ("int(ev_ctx.tyre_wear_multiplier)",
                     "int(ev_ctx.fuel_multiplier)",
                     "ev_ctx.mandatory_stops", "ev_ctx.weather", "ev_ctx.damage",
                     "ev_ctx.bop_enabled", "ev_ctx.tuning_allowed",
                     "ev_ctx.track", "ev_ctx.car"):
            assert frag in body, f"setup label not migrated: {frag}"

    def test_functional_gating_calls_intact(self, sbu_src):
        # Phase 3 update: the gating INPUTS moved to EventContext (signed-off
        # behaviour change — see tests/test_legacy_fanout_phase_3.py), but the
        # gating CALLS themselves are unchanged.
        body = _method_body(sbu_src, "_sync_setup_builder_from_event")
        assert "self._apply_setup_permissions(" in body
        assert "self._on_bop_toggled(" in body
        assert "self._rebound_setup_spinboxes(" in body

    def test_permission_call_signature_unchanged(self, sbu_src):
        body = _method_body(sbu_src, "_sync_setup_builder_from_event")
        # The permission call is still fed the _bop/_tuning/_cats trio.
        assert "self._apply_setup_permissions(_bop, _tuning, _cats)" in body


class TestStrategySyncMigration:
    def test_builds_event_context_and_labels_use_it(self, dash_src):
        body = _method_body(dash_src, "_sync_strategy_from_event")
        assert "ev_ctx = self._build_event_context()" in body
        for frag in ("int(ev_ctx.tyre_wear_multiplier)",
                     "int(ev_ctx.fuel_multiplier)",
                     "int(ev_ctx.refuel_rate_lps)",
                     "ev_ctx.track", "ev_ctx.car", "ev_ctx.race_type"):
            assert frag in body, f"strategy label not migrated: {frag}"

    def test_writer_still_called(self, dash_src):
        body = _method_body(dash_src, "_sync_strategy_from_event")
        assert "self._update_race_config()" in body

    def test_no_raw_strategy_wear_fuel_reads_left(self, dash_src):
        body = _method_body(dash_src, "_sync_strategy_from_event")
        assert 'sc.get("tyre_wear_multiplier"' not in body
        assert 'sc.get("fuel_mult"' not in body


# --------------------------------------------------------------------------- #
# 4. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_writers_and_fan_out_preserved(self, dash_src):
        body = _method_body(dash_src, "_on_event_set_active")
        assert 'strat = self._config.setdefault("strategy", {})' in body
        assert 'strat["track"]' in body

    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
