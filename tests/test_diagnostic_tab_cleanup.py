"""Diagnostic Tab Cleanup sprint — source-scan tests.

Proves the low-risk UI cleanup did exactly what it claims and nothing else:
the unreachable legacy per-segment review controls are gone (with no broken
references left behind), developer-facing labels are renamed, dead constants
are deleted, and everything that must NOT change (tab order, Home Dashboard,
diagnostic tabs, legacy compatibility, backend review functions) is intact.

All tests follow the project's no-Qt convention (source scans / pure imports).
"""

import re
from pathlib import Path

import pytest

from ui import product_flow as pf


ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tm_src():
    return (ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


# --------------------------------------------------------------------------- #
# 1. The 7 hidden legacy per-segment buttons are fully removed
# --------------------------------------------------------------------------- #
class TestLegacyReviewButtonsRemoved:
    DELETED_WIDGETS = (
        "_tm_btn_rev_confirm", "_tm_btn_rev_rename", "_tm_btn_rev_reject",
        "_tm_btn_rev_needs_laps", "_tm_btn_rev_split", "_tm_btn_rev_merge",
        "_tm_btn_rev_save", "_tm_lbl_rev_save_path",
    )
    DELETED_METHODS = (
        "_tm_review_confirm", "_tm_review_rename", "_tm_review_reject",
        "_tm_review_needs_laps", "_tm_review_split", "_tm_review_merge",
        "_tm_review_save", "_tm_refresh_review_buttons",
        "_tm_refresh_approval_panel",
    )

    def test_widgets_gone_from_all_ui_modules(self, tm_src, dash_src):
        for name in self.DELETED_WIDGETS:
            assert name not in tm_src, f"{name} still referenced in track_modelling_ui.py"
            assert name not in dash_src, f"{name} still referenced in dashboard.py"

    def test_handler_methods_gone(self, tm_src, dash_src):
        for name in self.DELETED_METHODS:
            assert not re.search(rf"def {name}\(", tm_src), (
                f"{name}() still defined in track_modelling_ui.py")
            assert name not in tm_src, (
                f"{name} still referenced in track_modelling_ui.py — broken call site")
            assert name not in dash_src, f"{name} still referenced in dashboard.py"

    def test_no_broken_getattr_references_to_deleted_names(self, tm_src, dash_src):
        # Any getattr(self, "<deleted name>") left behind is a silent dead path.
        for src, fname in ((tm_src, "track_modelling_ui.py"),
                           (dash_src, "dashboard.py")):
            for name in self.DELETED_WIDGETS + self.DELETED_METHODS:
                assert f'"{name}"' not in src and f"'{name}'" not in src, (
                    f"string reference to deleted {name} remains in {fname}")

    def test_dead_imports_removed(self, tm_src):
        for alias in ("_get_review_btns", "_seg_confirm", "_seg_rename",
                      "_seg_reject", "_seg_needs_laps", "_seg_split",
                      "_seg_merge", "_export_seg_review", "_rev_btn_"):
            assert alias not in tm_src, (
                f"dead import/style alias {alias} remains in track_modelling_ui.py")

    def test_detection_review_model_creation_still_present(self, tm_src):
        # The whole-model workflow keeps building the review model from
        # detection — only the per-segment UI was deleted.
        assert "_create_seg_review" in tm_src
        assert "self._tm_review_result" in tm_src

    def test_backend_review_functions_kept_and_importable(self):
        # The pure data/vm layers are intentionally retained (they have their
        # own test coverage) — the cleanup removed UI only.
        from data.track_segment_review import (  # noqa: F401
            confirm_segment, rename_segment, reject_segment,
            mark_needs_more_laps, mark_split_required, mark_merge_required,
            export_review_json,
        )
        from ui.track_modelling_vm import get_review_button_states  # noqa: F401


# --------------------------------------------------------------------------- #
# 2. Renamed developer-facing labels
# --------------------------------------------------------------------------- #
class TestRenamedLabels:
    def test_session_match_key_replaces_race_config_id(self, dash_src):
        assert '"Session Match Key:"' in dash_src
        assert '"Race Config ID:"' not in dash_src

    def test_diagnostics_time_left_replaces_rem_clk(self, dash_src):
        assert "Time left:" in dash_src
        assert "Rem(clk)" not in dash_src

    def test_diagnostics_raw_field_uses_real_field_name(self, dash_src):
        assert "remaining_time_ms:" in dash_src
        assert "rem_ms(raw)" not in dash_src

    def test_voice_queue_replaces_ann_queue(self, dash_src):
        assert "Voice queue:" in dash_src
        assert "Ann queue" not in dash_src

    def test_pip_install_tooltip_removed(self, dash_src):
        assert "pip install" not in dash_src

    def test_window_title_uses_product_name(self, dash_src):
        assert 'setWindowTitle("Next Gear Racing Pit Crew")' in dash_src
        assert 'setWindowTitle("GT7 VR Dashboard")' not in dash_src


# --------------------------------------------------------------------------- #
# 3. Guide content fixed
# --------------------------------------------------------------------------- #
class TestGuideContent:
    def test_guide_title_uses_product_name(self, dash_src):
        assert "Next Gear Racing Pit Crew — User Guide" in dash_src
        assert "GT7 VR Dashboard — User Guide" not in dash_src

    def test_stale_dashboard_step_replaced_by_home(self, dash_src):
        # Step 8 described a "Dashboard" tab with quick-link buttons that never
        # existed; it now describes the real Home tab.
        assert "Dashboard — event and session overview" not in dash_src
        assert "quick-link buttons" not in dash_src
        assert "Home — race engineer overview" in dash_src
        assert "Race Engineer Command Centre" in dash_src

    def test_api_key_bullet_points_at_strategy_builder(self, dash_src):
        # The only editable API-key field lives on the Strategy Builder tab —
        # the Guide must not claim it is in Settings.
        m = re.search(r"<li><b>API Key</b>.*?</li>", dash_src, re.DOTALL)
        assert m, "API Key bullet missing from the Guide"
        assert "Strategy Builder" in m.group(0)

    def test_guide_explains_tool_tabs(self, dash_src):
        assert "Tool tabs (⚙)" in dash_src
        assert "safe to" in dash_src  # "safe to ignore" wording

    def test_dead_telemetry_reference_constant_deleted(self, dash_src):
        assert not re.search(r"^_TELEMETRY_REFERENCE_HTML\s*=", dash_src, re.M), (
            "_TELEMETRY_REFERENCE_HTML constant should be deleted (it was never rendered)")


# --------------------------------------------------------------------------- #
# 4. Everything that must NOT change
# --------------------------------------------------------------------------- #
class TestNothingElseChanged:
    def test_tab_order_pinned(self, dash_src):
        # Home Dashboard Promotion (2026-07-03): Home leads at # 0; the
        # diagnostic-cleanup tabs shifted down one but kept their relative order.
        for needle in (
            'self._build_home_tab(),             "Home")             # 0',
            '"Live Race Engineer") # 1',
            '"Event Planner")   # 2',
            '"Telemetry")        # 7',
            '"Diagnostics")      # 8',
            '"AI Log")           # 12',
            'self._build_track_modelling_tab(), "Track Modelling")  # 13',
        ):
            assert needle in dash_src, f"tab wiring changed: {needle}"

    def test_on_tab_changed_dispatches_unchanged(self, dash_src):
        # Tab Navigation Refactor (2026-07-03): dispatch moved from raw indices
        # to stable tab keys — the same 8 per-tab behaviours must still fire.
        body = _method_body(dash_src, "_on_tab_changed")
        for frag in ("TAB_HISTORY", "TAB_SETUP_BUILDER", "TAB_STRATEGY_BUILDER",
                     "TAB_PRACTICE_REVIEW", "TAB_TELEMETRY", "TAB_AI_LOG",
                     "TAB_TRACK_MODELLING", "TAB_HOME",
                     "_refresh_history", "_sync_setup_builder_from_event",
                     "_sync_strategy_from_event", "_sync_practice_from_event",
                     "_refresh_telemetry_context", "_flush_ai_log_pending_select",
                     "_tm_on_tab_shown", "_home_refresh"):
            assert frag in body

    def test_diagnostic_tabs_still_built(self, dash_src):
        for builder in ("_build_telemetry_tab", "_build_debug_tab",
                        "_build_ai_log_tab", "_build_track_modelling_tab"):
            assert f"self.{builder}()" in dash_src

    def test_product_flow_roles_unchanged(self):
        assert set(pf.diagnostic_tabs()) == {
            "Telemetry", "Diagnostics", "AI Log", "Track Modelling",
        }
        assert pf.TAB_ROLES.get("Home") == pf.ROLE_WORKFLOW

    def test_home_dashboard_intact(self, dash_src):
        for frag in ("_build_home_tab", "_build_home_dashboard_state",
                     "_home_refresh_if_visible", "build_home_dashboard_state"):
            assert frag in dash_src

    def test_legacy_strategy_fanout_untouched(self, tm_src, dash_src):
        # The high-risk config["strategy"] fan-outs are explicitly out of
        # scope: the Track Modelling combo writer and the event Set-as-Active
        # writer must both still exist (removal is its own future sprint).
        assert re.search(r'\["strategy"\]\s*\[\s*"track_location_id"\s*\]|'
                         r'strat\["track_location_id"\]|'
                         r'"track_location_id"\]\s*=', tm_src), (
            "Track Modelling legacy id fan-out unexpectedly changed")
        assert 'strat["track"]' in dash_src, (
            "_on_event_set_active fan-out unexpectedly changed")

    def test_no_new_strategy_writes_in_touched_areas(self, dash_src):
        # The areas this sprint touched are display-only; none may write
        # config["strategy"].
        for name in ("_build_guide_tab", "_build_debug_tab"):
            body = _method_body(dash_src, name)
            assert 'setdefault("strategy"' not in body
            assert re.search(r'config\[.strategy.\]\s*\[', body) is None

    def test_api_key_field_still_exists_for_ai_callers(self, dash_src):
        # No duplicate existed to remove; the single editable field must stay
        # (every AI caller reads self._ai_api_key.text()).
        assert "self._ai_api_key = QLineEdit" in dash_src
        assert '"Anthropic API Key:"' in dash_src
