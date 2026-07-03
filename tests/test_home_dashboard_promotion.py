"""Home Dashboard Promotion sprint — Home-first ordering + click-to-navigate.

Follows the project's no-Qt convention:
  1. Pure unit tests of the card→tab navigation mapping in
     ui.home_dashboard_vm (no PyQt6).
  2. Source-scan tests that ui/dashboard.py makes Home the first tab and the
     default landing page, and that the Home cards navigate via select_tab with
     stable keys only — no new raw indices, no domain-state mutation, no
     dependence on the (⚙-decorated) visible labels.

The order-pinning invariants themselves live in
tests/test_tab_navigation_registry.py (updated for the promotion); this file
adds the promotion-specific behaviour.
"""

import re
from pathlib import Path

import pytest

from ui import home_dashboard_vm as hd
from ui import product_flow as pf
from ui import tab_registry as tr


ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


# --------------------------------------------------------------------------- #
# 1. Home is the first tab / default landing page
# --------------------------------------------------------------------------- #
class TestHomeIsFirst:
    def test_home_leads_default_order(self):
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME
        assert tr.build_default_registry().index_of(tr.TAB_HOME) == 0

    def test_home_addtab_is_first_in_source_order(self, dash_src):
        # The Home addTab call must be the FIRST of the fourteen addTab calls.
        titles = re.findall(r'self\._tabs\.addTab\([^,]+,\s*"([^"]+)"\)', dash_src)
        assert titles, "no addTab calls found"
        assert titles[0] == "Home", f"first tab is {titles[0]!r}, expected Home"
        assert titles.count("Home") == 1

    def test_app_selects_home_by_default(self, dash_src):
        # The app opens on Home via the named helper — never a raw index.
        assert "self.select_tab(TAB_HOME)" in dash_src

    def test_home_rendered_once_at_startup(self, dash_src):
        # Home is the landing tab, so it is refreshed once during __init__
        # (selecting an already-current index emits no signal).
        init_body = _method_body(dash_src, "__init__")
        assert "self._home_refresh()" in init_body

    def test_default_order_still_mirrors_addtab_sequence(self, dash_src):
        titles = re.findall(r'self\._tabs\.addTab\([^,]+,\s*"([^"]+)"\)', dash_src)
        expected = [tr.TAB_BASE_TITLES[k] for k in tr.DEFAULT_TAB_ORDER]
        assert titles == expected


# --------------------------------------------------------------------------- #
# 2. Card → tab navigation mapping (pure)
# --------------------------------------------------------------------------- #
class TestCardTabMapping:
    def test_every_card_maps_to_the_expected_tab(self):
        assert hd.CARD_TAB_KEYS == {
            hd.CARD_RACE_SETUP: tr.TAB_EVENT_PLANNER,
            hd.CARD_TRACK: tr.TAB_TRACK_MODELLING,
            hd.CARD_SETUP: tr.TAB_SETUP_BUILDER,
            hd.CARD_STRATEGY: tr.TAB_STRATEGY_BUILDER,
            hd.CARD_AI_SAFETY: tr.TAB_AI_LOG,
        }

    def test_mapping_covers_every_card_in_card_order(self):
        for key in hd.CARD_ORDER:
            assert key in hd.CARD_TAB_KEYS, f"card {key} has no navigation target"

    def test_mapping_values_are_real_registry_keys(self):
        # Values must be stable keys the registry resolves — never visible
        # labels — so the ⚙ decoration can never affect navigation.
        reg = tr.build_default_registry()
        for card_key, tab_key in hd.CARD_TAB_KEYS.items():
            assert reg.has(tab_key), f"{card_key} → {tab_key!r} is not a tab key"
            assert tab_key in tr.TAB_BASE_TITLES

    def test_tab_key_for_card_helper(self):
        assert hd.tab_key_for_card(hd.CARD_SETUP) == tr.TAB_SETUP_BUILDER
        assert hd.tab_key_for_card(hd.CARD_STRATEGY) == tr.TAB_STRATEGY_BUILDER

    def test_tab_key_for_unknown_card_fails_safely(self):
        assert hd.tab_key_for_card("no_such_card") is None
        assert hd.tab_key_for_card("") is None
        assert hd.tab_key_for_card(None) is None

    def test_ai_safety_targets_a_diagnostic_tool_tab(self):
        # AI Input Safety opens the AI Log tool tab (a ⚙ diagnostic tab).
        assert hd.CARD_TAB_KEYS[hd.CARD_AI_SAFETY] == tr.TAB_AI_LOG
        assert "AI Log" in pf.diagnostic_tabs()


# --------------------------------------------------------------------------- #
# 3. Dashboard click-to-navigate wiring (source-scan)
# --------------------------------------------------------------------------- #
class TestNavigationWiring:
    def test_home_navigate_uses_select_tab_and_guards(self, dash_src):
        body = _method_body(dash_src, "_home_navigate")
        assert "self.select_tab(tab_key)" in body
        assert "has_tab" in body, "must fail safely on an unavailable tab"

    def test_home_navigate_changes_tab_only(self, dash_src):
        # Navigation must not mutate domain state, start AI/telemetry/
        # calibration, or save anything.
        for name in ("_home_navigate", "_home_navigate_next_action",
                     "_home_update_next_action_button"):
            body = _method_body(dash_src, name)
            assert re.search(r'config\[.strategy.\]\s*\[', body) is None, (
                f"{name} writes into config['strategy']")
            assert 'setdefault("strategy"' not in body
            assert "_persist_config" not in body
            assert "save_" not in body and "upsert" not in body
            for forbidden in ("_run_ai", "_run_build_setup", "_run_practice",
                              "start_tracker", "_start_calibration",
                              "_launch_", "QThread", "QTimer"):
                assert forbidden not in body, f"{name} triggers {forbidden}"

    def test_cards_wire_buttons_by_stable_key(self, dash_src):
        body = _method_body(dash_src, "_build_home_tab")
        # The per-card button resolves its target through the pure mapping and
        # calls _home_navigate with a KEY captured in the lambda default.
        assert "tab_key_for_card(key)" in body
        assert "self._home_navigate(k)" in body

    def test_next_action_button_maps_name_via_key_for_title(self, dash_src):
        body = _method_body(dash_src, "_home_update_next_action_button")
        assert "key_for_title" in body, (
            "the flow summary's tab NAME must be mapped to a key, not compared "
            "to a visible label")
        assert "has_tab" in body

    def test_nav_button_text_uses_undecorated_titles(self, dash_src):
        body = _method_body(dash_src, "_home_nav_button_text")
        assert "TAB_BASE_TITLES" in body, (
            "button labels must come from undecorated base titles, not the ⚙ "
            "tab labels")

    def test_no_new_raw_setcurrentindex(self, dash_src):
        # The only permitted _tabs.setCurrentIndex site is still select_tab(idx).
        calls = re.findall(r"_tabs\.setCurrentIndex\(([^)]*)\)", dash_src)
        assert calls == ["idx"], f"unexpected setCurrentIndex sites: {calls}"


# --------------------------------------------------------------------------- #
# 4. Diagnostics preserved
# --------------------------------------------------------------------------- #
class TestDiagnosticsPreserved:
    def test_all_diagnostic_tabs_still_built(self, dash_src):
        for builder in ("_build_telemetry_tab", "_build_debug_tab",
                        "_build_ai_log_tab", "_build_track_modelling_tab"):
            assert f"self.{builder}()" in dash_src

    def test_tool_tab_markers_still_applied(self, dash_src):
        assert "_apply_product_flow_tab_markers()" in dash_src

    def test_diagnostic_set_unchanged(self):
        assert set(pf.diagnostic_tabs()) == {
            "Telemetry", "Diagnostics", "AI Log", "Track Modelling",
        }
