"""Tab Navigation Refactor sprint — named tab registry + dispatch tests.

Two kinds of tests, both following the project's no-Qt convention:
  1. Pure unit tests of ui.tab_registry (no PyQt6).
  2. Source-scan tests that ui/dashboard.py now dispatches and navigates by
     stable tab key — with NO raw hard-coded tab indices left — while the
     visible tab order, the Home tab position, and the diagnostic tabs are
     all unchanged.
"""

import re
from pathlib import Path

import pytest

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
# 1. Registry — keys, order, lookups
# --------------------------------------------------------------------------- #
class TestRegistryKeys:
    def test_every_current_tab_has_a_stable_key(self):
        assert len(tr.DEFAULT_TAB_ORDER) == 14
        assert len(set(tr.DEFAULT_TAB_ORDER)) == 14, "duplicate tab keys"
        for key in tr.DEFAULT_TAB_ORDER:
            assert key in tr.TAB_BASE_TITLES, f"no base title for {key}"

    def test_base_titles_match_product_flow_roles(self):
        # The registry's canonical titles and product_flow's role table must
        # describe the same set of tabs — one can't drift from the other.
        assert set(tr.TAB_BASE_TITLES.values()) == set(pf.TAB_ROLES.keys())

    def test_current_visual_order_is_preserved(self):
        # Indices 0-13 exactly as the app has shipped them since the Home
        # Dashboard sprint appended Home at the end.
        expected = (
            tr.TAB_LIVE, tr.TAB_EVENT_PLANNER, tr.TAB_GARAGE,
            tr.TAB_SETUP_BUILDER, tr.TAB_PRACTICE_REVIEW,
            tr.TAB_STRATEGY_BUILDER, tr.TAB_TELEMETRY, tr.TAB_DIAGNOSTICS,
            tr.TAB_GUIDE, tr.TAB_SETTINGS, tr.TAB_HISTORY, tr.TAB_AI_LOG,
            tr.TAB_TRACK_MODELLING, tr.TAB_HOME,
        )
        assert tr.DEFAULT_TAB_ORDER == expected

    def test_home_remains_last_this_sprint(self):
        assert tr.DEFAULT_TAB_ORDER[-1] == tr.TAB_HOME
        assert tr.DEFAULT_TAB_ORDER.index(tr.TAB_HOME) == 13

    def test_default_order_matches_addtab_calls_in_dashboard(self, dash_src):
        # The registry is positional, so DEFAULT_TAB_ORDER must mirror the
        # addTab creation order EXACTLY. Extract the titles from the source
        # and compare sequence-to-sequence.
        titles = re.findall(r'self\._tabs\.addTab\([^,]+,\s*"([^"]+)"\)', dash_src)
        assert titles, "no addTab calls found"
        expected_titles = [tr.TAB_BASE_TITLES[k] for k in tr.DEFAULT_TAB_ORDER]
        assert titles == expected_titles, (
            "DEFAULT_TAB_ORDER no longer mirrors the addTab creation order — "
            "update ui/tab_registry.py and the addTab block together")


class TestRegistryLookups:
    def test_key_to_index_round_trip(self):
        reg = tr.build_default_registry()
        for i, key in enumerate(tr.DEFAULT_TAB_ORDER):
            assert reg.index_of(key) == i
            assert reg.key_at(i) == key

    def test_count_matches_tab_count(self):
        assert tr.build_default_registry().count == len(tr.DEFAULT_TAB_ORDER)

    def test_missing_key_fails_safely(self):
        reg = tr.build_default_registry()
        assert reg.index_of("no_such_tab") == -1
        assert reg.index_of(None) == -1
        assert reg.index_of(42) == -1
        assert reg.has("no_such_tab") is False

    def test_out_of_range_index_fails_safely(self):
        reg = tr.build_default_registry()
        assert reg.key_at(-1) is None
        assert reg.key_at(99) is None
        assert reg.key_at("garbage") is None
        assert reg.key_at(None) is None

    def test_duplicate_registration_is_a_safe_noop(self):
        reg = tr.TabRegistry()
        assert reg.register("a") == 0
        assert reg.register("b") == 1
        assert reg.register("a") == 0  # returns existing index
        assert reg.count == 2
        assert reg.keys() == ("a", "b")

    def test_empty_registry_is_safe(self):
        reg = tr.TabRegistry()
        assert reg.count == 0
        assert reg.key_at(0) is None
        assert reg.index_of(tr.TAB_HOME) == -1


class TestDecoratedTitles:
    def test_decorated_titles_resolve_to_keys(self):
        # The ⚙ tool-tab decoration must never break the title→key mapping.
        for key, title in tr.TAB_BASE_TITLES.items():
            decorated = pf.decorate_tab_title(title)
            assert tr.key_for_title(decorated) == key, (
                f"decorated title {decorated!r} failed to resolve to {key}")

    def test_undecorated_titles_resolve_too(self):
        assert tr.key_for_title("Telemetry") == tr.TAB_TELEMETRY
        assert tr.key_for_title("Home") == tr.TAB_HOME

    def test_unknown_title_fails_safely(self):
        assert tr.key_for_title("Not A Tab") is None
        assert tr.key_for_title("") is None
        assert tr.key_for_title(None) is None

    def test_registry_lookup_is_positional_not_label_based(self):
        # The primary mechanism must be registration order — a registry built
        # from keys knows nothing about labels at all.
        reg = tr.build_default_registry()
        assert reg.key_at(6) == tr.TAB_TELEMETRY  # decorated "⚙ Telemetry" in the UI

    def test_module_is_pure(self):
        src = (ROOT / "ui" / "tab_registry.py").read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import PyQt6|from PyQt6)", src, re.M), (
            "tab_registry must not import PyQt6")
        assert "config" not in src.lower().replace("configuration", ""), (
            "tab_registry must not touch config")


# --------------------------------------------------------------------------- #
# 2. Dashboard wiring — key-based dispatch, no raw indices
# --------------------------------------------------------------------------- #
class TestDispatchByKey:
    def test_on_tab_changed_has_no_raw_index_comparisons(self, dash_src):
        body = _method_body(dash_src, "_on_tab_changed")
        assert not re.search(r"index\s*==\s*\d", body), (
            "_on_tab_changed still compares against raw numeric indices")

    def test_on_tab_changed_dispatches_by_key_with_same_behaviours(self, dash_src):
        body = _method_body(dash_src, "_on_tab_changed")
        pairs = (
            ("TAB_HISTORY", "_refresh_history"),
            ("TAB_SETUP_BUILDER", "_sync_setup_builder_from_event"),
            ("TAB_STRATEGY_BUILDER", "_sync_strategy_from_event"),
            ("TAB_PRACTICE_REVIEW", "_sync_practice_from_event"),
            ("TAB_TELEMETRY", "_refresh_telemetry_context"),
            ("TAB_AI_LOG", "_flush_ai_log_pending_select"),
            ("TAB_TRACK_MODELLING", "_tm_on_tab_shown"),
            ("TAB_HOME", "_home_refresh"),
        )
        for key, handler in pairs:
            assert key in body and handler in body, (
                f"dispatch pair {key} → {handler} missing from _on_tab_changed")

    def test_no_hardcoded_tab_jumps_remain(self, dash_src):
        # The only permitted _tabs.setCurrentIndex call site is inside
        # select_tab(); every navigation jump must go through it by key.
        calls = re.findall(r"_tabs\.setCurrentIndex\(([^)]*)\)", dash_src)
        assert calls == ["idx"], (
            f"unexpected _tabs.setCurrentIndex call sites: {calls} — "
            "navigate via select_tab(TAB_*) instead")
        assert not re.search(r"_tabs\.setCurrentIndex\(\s*\d", dash_src)

    def test_old_numeric_current_index_checks_gone(self, dash_src):
        assert not re.search(r"currentIndex\(\)\s*!=\s*\d", dash_src), (
            "a visibility check still compares currentIndex() to a raw number")

    def test_home_tab_index_attribute_retired(self, dash_src):
        assert "_home_tab_index" not in dash_src, (
            "_home_tab_index is superseded by the registry (TAB_HOME)")

    def test_jump_sites_use_named_navigation(self, dash_src):
        assert "self.select_tab(TAB_PRACTICE_REVIEW)" in dash_src  # History → Practice Review
        assert "self.select_tab(TAB_SETUP_BUILDER)" in dash_src    # Garage setup load
        assert "self.select_tab(TAB_EVENT_PLANNER)" in dash_src    # Garage → Event Planner

    def test_visibility_checks_use_keys(self, dash_src):
        flush = _method_body(dash_src, "_flush_ai_log_pending_select")
        assert "current_tab_key() != TAB_AI_LOG" in flush
        home = _method_body(dash_src, "_home_refresh_if_visible")
        assert "current_tab_key() != TAB_HOME" in home


class TestNavigationHelpers:
    def test_helpers_defined(self, dash_src):
        for name in ("get_tab_index", "has_tab", "current_tab_key", "select_tab"):
            assert re.search(rf"\n    def {name}\(", dash_src), f"{name}() missing"

    def test_select_tab_selects_via_registry_index(self, dash_src):
        body = _method_body(dash_src, "select_tab")
        assert "get_tab_index" in body
        assert "setCurrentIndex(idx)" in body
        # Unknown key → safe no-op returning False.
        assert "return False" in body

    def test_get_tab_index_safe_without_registry(self, dash_src):
        body = _method_body(dash_src, "get_tab_index")
        assert "-1" in body and "getattr" in body

    def test_registry_built_at_setup_with_count_guard(self, dash_src):
        assert "self._tab_registry = build_default_registry()" in dash_src
        assert "self._tab_registry.count != self._tabs.count()" in dash_src

    def test_helper_mapping_is_correct_for_jump_targets(self):
        # The indices select_tab() will resolve for this sprint's jump targets
        # (proves the behaviour of the migrated setCurrentIndex(4/3/1) calls).
        reg = tr.build_default_registry()
        assert reg.index_of(tr.TAB_PRACTICE_REVIEW) == 4
        assert reg.index_of(tr.TAB_SETUP_BUILDER) == 3
        assert reg.index_of(tr.TAB_EVENT_PLANNER) == 1
        assert reg.index_of(tr.TAB_AI_LOG) == 11
        assert reg.index_of(tr.TAB_HOME) == 13


# --------------------------------------------------------------------------- #
# 3. Nothing else changed
# --------------------------------------------------------------------------- #
class TestNothingElseChanged:
    def test_tab_order_pinned(self, dash_src):
        for needle in (
            '"Live Race Engineer") # 0',
            '"Event Planner")   # 1',
            '"Garage")           # 2',
            '"Setup Builder")    # 3',
            '"Practice Review")  # 4',
            '"Strategy Builder") # 5',
            '"Telemetry")        # 6',
            '"Diagnostics")      # 7',
            '"Guide")            # 8',
            '"Settings")         # 9',
            '"History")          # 10',
            '"AI Log")           # 11',
            'self._build_track_modelling_tab(), "Track Modelling")  # 12',
            'self._build_home_tab(),             "Home")             # 13',
        ):
            assert needle in dash_src, f"tab wiring changed: {needle}"

    def test_home_still_appended_after_track_modelling(self, dash_src):
        tm = dash_src.index('"Track Modelling")  # 12')
        home = dash_src.index('"Home")             # 13')
        assert home > tm

    def test_diagnostic_tabs_still_built_and_marked(self, dash_src):
        for builder in ("_build_telemetry_tab", "_build_debug_tab",
                        "_build_ai_log_tab", "_build_track_modelling_tab"):
            assert f"self.{builder}()" in dash_src
        # Tool-tab decoration still applied after registry creation.
        assert "_apply_product_flow_tab_markers()" in dash_src
        assert set(pf.diagnostic_tabs()) == {
            "Telemetry", "Diagnostics", "AI Log", "Track Modelling",
        }

    def test_navigation_helpers_write_no_state(self, dash_src):
        for name in ("get_tab_index", "has_tab", "current_tab_key",
                     "select_tab", "_on_tab_changed"):
            body = _method_body(dash_src, name)
            assert 'setdefault("strategy"' not in body
            assert re.search(r'config\[.strategy.\]\s*\[', body) is None, (
                f"{name} writes into config['strategy']")
            assert "_persist_config" not in body

    def test_legacy_fanouts_untouched(self, dash_src):
        # Out of scope for this sprint — the event fan-out must still exist.
        assert 'strat["track"]' in dash_src