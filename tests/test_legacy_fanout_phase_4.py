"""Legacy Fan-Out Removal Phase 4 — divergence elimination + last readers.

Two deliverables, both tested here:

1. **Re-sync on Save** — the Set-as-Active fan-out block was extracted verbatim
   into ``MainWindow._fanout_event_to_strategy`` (config-dict only: no tracker /
   advisor / query-listener / persist side effects), and ``_on_event_save`` now
   calls it when the saved event IS the active event. The DB event record and
   the ``config["strategy"]`` fan-out can therefore no longer diverge; the
   activation side effects remain exclusive to "Set as Active".

2. **Last minor readers migrated** — ``_get_mandatory_compounds`` (codes from
   ``EventContext.required_tyres`` mapped to display names via
   ``data.tyres.get_by_code``, the same mapping the fan-out writer used) and the
   setup tab's refuel / required-tyre / available-tyre labels + car spinbox
   rebind. ``_sync_setup_builder_from_event`` no longer reads
   ``config["strategy"]`` at all.

Writer retirement is explicitly deferred (documented in
docs/LEGACY_FANOUT_PHASE_4.md §5): ``car`` / ``config_id`` / the stint plan live
ONLY in the fan-out, and ~25 readers still consume it — with re-sync in place it
can no longer go stale, so retirement is a mechanical follow-up.
"""
from __future__ import annotations

import re
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data.event_context import build_event_context
from data.tyres import get_by_code

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
# 1. The extracted fan-out helper (real method bound to a widget stub)
# --------------------------------------------------------------------------- #
def _make_fanout_stub():
    from ui import dashboard as _dash_mod
    stub = MagicMock()
    stub._config = {"strategy": {
        # Strategy-PLAN fields the helper must NEVER touch:
        "car": "KeepMe", "config_id": "abc123",
        "stops": [{"lap": 5}], "fuel_burn_per_lap": 2.5,
    }}
    stub._evt_track.currentText.return_value = "Spa"
    stub._evt_race_type.currentText.return_value = "Timed Race"
    stub._evt_laps.value.return_value = 12
    stub._evt_duration.value.return_value = 30
    stub._evt_tyre_wear.value.return_value = 2
    stub._evt_fuel_mult.value.return_value = 3
    stub._evt_mand_pits.value.return_value = 1
    stub._evt_weather.currentText.return_value = "Fixed Dry"
    stub._evt_damage.currentText.return_value = "Light"
    stub._evt_refuel_rate.value.return_value = 5
    cb_on, cb_off = MagicMock(), MagicMock()
    cb_on.isChecked.return_value = True
    cb_off.isChecked.return_value = False
    stub._req_tyre_checks = {"RM": cb_on, "RS": cb_off}
    stub._avail_tyre_checks = {"RM": cb_on, "RH": cb_on, "RS": cb_off}
    stub._evt_bop.isChecked.return_value = True
    stub._evt_tuning.isChecked.return_value = False
    stub._tuning_cat_checks = {"suspension": cb_on, "aero": cb_off}
    stub._db = None
    stub._fanout_event_to_strategy = types.MethodType(
        _dash_mod.MainWindow._fanout_event_to_strategy, stub)
    return stub


class TestFanoutHelper:
    def test_writes_all_event_rule_fields(self):
        # Rule-Cache Deletion (2026-07-04): the helper now writes ONLY the
        # working-config core; the 12 event-rule cache fields are deleted
        # (DB-only via EventContext). This test pins both halves.
        stub = _make_fanout_stub()
        strat = stub._fanout_event_to_strategy("Race A")
        assert strat["track"] == "Spa"
        assert strat["race_type"] == "timed"          # normalised token
        assert strat["laps"] == 12 and strat["total_laps"] == 12
        assert strat["race_duration_minutes"] == 30
        assert strat["event_id"] == 0                 # db is None
        for gone in ("tyre_wear_multiplier", "fuel_mult", "mandatory_stops",
                     "weather", "damage", "refuel_speed_lps", "required_tyres",
                     "mandatory_compounds", "avail_tyres", "bop", "tuning",
                     "allowed_tuning_categories"):
            assert gone not in strat, f"rule-cache field {gone} written again"

    def test_never_touches_strategy_plan_fields(self):
        stub = _make_fanout_stub()
        strat = stub._fanout_event_to_strategy("Race A")
        assert strat["car"] == "KeepMe"
        assert strat["config_id"] == "abc123"
        assert strat["stops"] == [{"lap": 5}]
        assert strat["fuel_burn_per_lap"] == 2.5

    def test_returns_the_config_strategy_dict(self):
        stub = _make_fanout_stub()
        strat = stub._fanout_event_to_strategy("Race A")
        assert strat is stub._config["strategy"]

    def test_config_dict_only_no_side_effects(self):
        stub = _make_fanout_stub()
        stub._fanout_event_to_strategy("Race A")
        stub._persist_config.assert_not_called()
        stub._sync_setup_builder_from_event.assert_not_called()
        stub._sync_strategy_from_event.assert_not_called()

    def test_lap_race_type_normalised(self):
        stub = _make_fanout_stub()
        stub._evt_race_type.currentText.return_value = "Lap Race"
        strat = stub._fanout_event_to_strategy("Race A")
        assert strat["race_type"] == "lap"


# --------------------------------------------------------------------------- #
# 2. Save-path re-sync — guarded, config-only (source-scan)
# --------------------------------------------------------------------------- #
class TestSavePathResync:
    def test_save_resyncs_fanout_for_active_event_only(self, dash_src):
        body = _method_body(dash_src, "_on_event_save")
        assert 'if name == self._config.get("active_event_id"):' in body
        assert "self._fanout_event_to_strategy(name)" in body
        # Re-sync happens BEFORE the persist so the fresh fan-out is written out.
        assert body.index("self._fanout_event_to_strategy(name)") \
            < body.index("self._persist_config()")

    def test_save_path_stays_config_only(self, dash_src):
        # Activation side effects must remain exclusive to Set-as-Active.
        body = _method_body(dash_src, "_on_event_save")
        for forbidden in ("set_race_config", "_driving_advisor",
                          "_query_listener", "_sync_setup_builder_from_event",
                          "_sync_strategy_from_event", "_apply_setup_permissions"):
            assert forbidden not in body, f"_on_event_save gained {forbidden}"

    def test_set_active_keeps_its_side_effects(self, dash_src):
        body = _method_body(dash_src, "_on_event_set_active")
        assert "self._fanout_event_to_strategy(evt_name)" in body
        for frag in ("set_race_config", "_driving_advisor",
                     "_sync_setup_builder_from_event",
                     "_sync_strategy_from_event", "_persist_config"):
            assert frag in body, f"Set-as-Active lost {frag}"

    def test_set_active_has_no_inline_fanout_left(self, dash_src):
        body = _method_body(dash_src, "_on_event_set_active")
        assert 'strat["track"]' not in body, (
            "the fan-out block should live only in _fanout_event_to_strategy")


# --------------------------------------------------------------------------- #
# 3. Last readers migrated
# --------------------------------------------------------------------------- #
class TestMandatoryCompoundsMigrated:
    def test_reads_event_context_and_maps_codes_to_names(self, dash_src):
        body = _method_body(dash_src, "_get_mandatory_compounds")
        assert "_build_event_context().required_tyres" in body
        assert "get_by_code" in body
        assert 'get("mandatory_compounds"' not in body

    def test_byte_identical_to_old_string_parse_when_in_sync(self):
        # The fan-out wrote mandatory_compounds = ", ".join(names from codes);
        # the old reader split/upper-cased it. The new reader maps the same
        # codes (via EventContext.required_tyres) through the same name table.
        codes = ["RM", "RS"]
        fanout_string = ", ".join(get_by_code(c).name for c in codes)
        old = [c.strip().upper() for c in fanout_string.split(",") if c.strip()]
        ctx = build_event_context(
            event={"id": 1, "name": "E", "track": "Spa", "req_tyres": codes},
            strategy={"track": "Spa", "required_tyres": codes,
                      "mandatory_compounds": fanout_string},
        )
        new = [get_by_code(c).name.upper() for c in ctx.required_tyres
               if get_by_code(c)]
        assert new == old == ["RACING MEDIUM", "RACING SOFT"]

    def test_empty_when_no_required_tyres(self):
        ctx = build_event_context(strategy={"track": "Spa"})
        assert [get_by_code(c) for c in ctx.required_tyres] == []


class TestSetupSyncFullyOffFanOut:
    def test_no_config_strategy_reads_left(self, sbu_src):
        body = _method_body(sbu_src, "_sync_setup_builder_from_event")
        assert 'config.get("strategy"' not in body, (
            "_sync_setup_builder_from_event should no longer read "
            "config['strategy'] at all")

    def test_last_labels_read_event_context(self, sbu_src):
        # Amendment B (Setup Builder Engineering Validation Gate sprint): the
        # Race Conditions group (including refuel/req/avail labels) was removed.
        # The Phase 4 refuel/tyre display reads are therefore also gone.
        # The spinbox rebind call (functional side effect) must still be present.
        body = _method_body(sbu_src, "_sync_setup_builder_from_event")
        # Display-only reads that belonged to the removed RC labels are gone:
        assert "int(ev_ctx.refuel_rate_lps)" not in body, (
            "Amendment B: refuel label read should be removed with RC group"
        )
        assert '", ".join(ev_ctx.required_tyres)' not in body, (
            "Amendment B: required tyres label read should be removed with RC group"
        )
        assert '", ".join(ev_ctx.available_tyres)' not in body, (
            "Amendment B: available tyres label read should be removed with RC group"
        )
        # Functional side effect: spinbox rebind is still called.
        assert "self._rebound_setup_spinboxes(ev_ctx.car or \"\")" in body

    def test_label_values_byte_identical_in_sync(self):
        event = {"id": 1, "name": "E", "track": "Spa",
                 "refuel_rate_lps": 5, "req_tyres": ["RM"],
                 "avail_tyres": ["RM", "RH"]}
        strategy = {"track": "Spa", "car": "Porsche 963",
                    "refuel_speed_lps": 5, "required_tyres": ["RM"],
                    "avail_tyres": ["RM", "RH"]}
        ctx = build_event_context(event=event, strategy=strategy)
        # OLD (verbatim): f"{sc.get('refuel_speed_lps', 10)} L/s";
        # ", ".join(sc.get("required_tyres", [])); ", ".join(avail)
        assert f"{int(ctx.refuel_rate_lps)} L/s" == f"{strategy['refuel_speed_lps']} L/s"
        assert ", ".join(ctx.required_tyres) == ", ".join(strategy["required_tyres"])
        assert ", ".join(ctx.available_tyres) == ", ".join(strategy["avail_tyres"])
        assert (ctx.car or "") == strategy["car"]


# --------------------------------------------------------------------------- #
# 4. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_track_modelling_combo_writer_untouched(self):
        tm_src = (ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")
        assert 'setdefault("strategy", {})["track_location_id"]' in tm_src
        assert 'setdefault("strategy", {})["layout_id"]' in tm_src

    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
