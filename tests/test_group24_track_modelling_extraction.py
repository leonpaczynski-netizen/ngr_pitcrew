"""Acceptance tests — Track Modelling Tab Extraction Refactor.

Covers all acceptance criteria for the refactor that moved all _tm_* methods,
_build_track_modelling_tab(), state initialisations, and
_tm_ai_corner_verify_signal out of dashboard.py and into
ui/track_modelling_ui.py as TrackModellingMixin.

ACs verified here:
  AC1 — track_modelling_ui.py structure (class, methods, signal, state attrs)
  AC2 — dashboard.py class declaration and absence of _tm_ method definitions
  AC3 — _on_tab_changed() and signal connection remain in dashboard.py
  AC4 — _live_try_load_active_event_map() removed (Group A cleanup)
  AC6 — mixin contains >= 1700 lines (proxy for >= 2554 lines removed)
  AC7 — zero self._db references in the mixin
"""
import re
import pathlib

import pytest

ROOT = pathlib.Path(__file__).parent.parent
DASHBOARD_SRC = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
MIXIN_SRC = (ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC1 — ui/track_modelling_ui.py structure
# ---------------------------------------------------------------------------

class TestAC1MixinStructure:
    """AC1: track_modelling_ui.py exists and contains the expected structure."""

    def test_file_exists(self):
        assert (ROOT / "ui" / "track_modelling_ui.py").is_file(), (
            "ui/track_modelling_ui.py does not exist"
        )

    def test_TrackModellingMixin_class_declared(self):
        assert re.search(r"^class TrackModellingMixin", MIXIN_SRC, re.MULTILINE), (
            "TrackModellingMixin class not found in track_modelling_ui.py"
        )

    def test_tm_method_count_at_least_46(self):
        # Floor was 54 at extraction time (Group 24). Diagnostic Tab Cleanup
        # (2026-07-03) deleted 9 unreachable legacy methods — the 7 hidden
        # per-segment review handlers (_tm_review_confirm/rename/reject/
        # needs_laps/split/merge/save), _tm_refresh_review_buttons, and the
        # no-op _tm_refresh_approval_panel — lowering the floor to 46.
        hits = re.findall(r"^\s+def _tm_", MIXIN_SRC, re.MULTILINE)
        assert len(hits) >= 46, (
            f"Expected >= 46 _tm_ methods in mixin, found {len(hits)}"
        )

    def test_build_track_modelling_tab_in_mixin(self):
        assert re.search(r"def _build_track_modelling_tab\(", MIXIN_SRC), (
            "_build_track_modelling_tab() not found in track_modelling_ui.py"
        )

    def test_live_try_load_active_event_map_removed(self):
        # Group A cleanup: _live_try_load_active_event_map() was deleted because
        # the Live-tab map widget was removed.
        assert not re.search(r"def _live_try_load_active_event_map\(", MIXIN_SRC), (
            "_live_try_load_active_event_map() must not exist in track_modelling_ui.py "
            "after Group A cleanup"
        )

    def test_tm_ai_corner_verify_signal_in_mixin(self):
        assert "_tm_ai_corner_verify_signal" in MIXIN_SRC, (
            "_tm_ai_corner_verify_signal not found in track_modelling_ui.py"
        )

    def test_tm_ai_corner_verify_signal_is_pyqtSignal(self):
        # Must be declared as a class-level pyqtSignal, not just referenced
        assert re.search(
            r"_tm_ai_corner_verify_signal\s*=\s*pyqtSignal\(", MIXIN_SRC
        ), "_tm_ai_corner_verify_signal is not declared as pyqtSignal in mixin"

    def test_tm_state_attrs_initialised_in_mixin(self):
        """The original state init block (lines 2568-2582 of dashboard.py) must
        be present in the mixin — verified by checking a representative sample."""
        required_attrs = [
            "_tm_seed_result",
            "_tm_detection_result",
            "_tm_review_result",
            "_tm_resolver_result",
            "_tm_station_map",
        ]
        missing = [a for a in required_attrs if f"self.{a}" not in MIXIN_SRC]
        assert not missing, (
            f"State attribute(s) missing from mixin: {missing}"
        )


# ---------------------------------------------------------------------------
# AC2 — dashboard.py class declaration and absence of _tm_ method definitions
# ---------------------------------------------------------------------------

class TestAC2DashboardClean:
    """AC2: MainWindow inherits TrackModellingMixin; no _tm_ defs remain."""

    def test_TrackModellingMixin_in_class_declaration(self):
        m = re.search(
            r"^class (Main|Dashboard)Window\(.*?\)", DASHBOARD_SRC, re.MULTILINE
        )
        assert m is not None, "MainWindow / DashboardWindow class not found in dashboard.py"
        assert "TrackModellingMixin" in m.group(0), (
            f"TrackModellingMixin not in class declaration: {m.group(0)}"
        )

    def test_no_tm_method_definitions_in_dashboard(self):
        hits = re.findall(r"^\s+def _tm_", DASHBOARD_SRC, re.MULTILINE)
        assert len(hits) == 0, (
            f"Found {len(hits)} _tm_ method definition(s) still in dashboard.py — "
            f"expected 0. Methods: {hits[:5]}"
        )

    def test_build_track_modelling_tab_not_in_dashboard(self):
        assert not re.search(r"def _build_track_modelling_tab\(", DASHBOARD_SRC), (
            "_build_track_modelling_tab() is still defined in dashboard.py"
        )


# ---------------------------------------------------------------------------
# AC3 — _on_tab_changed() and signal connection remain in dashboard.py
# ---------------------------------------------------------------------------

class TestAC3TabChangedInDashboard:
    """AC3: _on_tab_changed() and tab signal connection stay in dashboard.py."""

    def test_on_tab_changed_defined_in_dashboard(self):
        assert re.search(r"def _on_tab_changed\(", DASHBOARD_SRC), (
            "_on_tab_changed() not found in dashboard.py"
        )

    def test_on_tab_changed_calls_tm_on_tab_shown(self):
        assert "_tm_on_tab_shown" in DASHBOARD_SRC, (
            "_tm_on_tab_shown not referenced in dashboard.py "
            "(expected call from _on_tab_changed)"
        )

    def test_tab_signal_connection_in_dashboard(self):
        # The tab widget's currentChanged signal must be wired in dashboard.py
        assert re.search(
            r"currentChanged.*connect|connect.*_on_tab_changed", DASHBOARD_SRC
        ), (
            "Tab currentChanged signal connection not found in dashboard.py"
        )


# ---------------------------------------------------------------------------
# AC4 — _live_try_load_active_event_map() removed by Group A cleanup
# ---------------------------------------------------------------------------

class TestAC4LiveTryLoadRemoved:
    """AC4: _live_try_load_active_event_map() deleted in Group A cleanup (Live-tab map removed)."""

    def test_method_not_in_mixin(self):
        assert not re.search(r"def _live_try_load_active_event_map\(", MIXIN_SRC), (
            "_live_try_load_active_event_map() must not exist in track_modelling_ui.py "
            "after Group A cleanup"
        )

    def test_method_not_defined_in_dashboard(self):
        assert not re.search(
            r"def _live_try_load_active_event_map\(", DASHBOARD_SRC
        ), (
            "_live_try_load_active_event_map() must not exist in dashboard.py "
            "after Group A cleanup"
        )


# ---------------------------------------------------------------------------
# AC6 — mixin line count confirms >= 1700 lines extracted
# ---------------------------------------------------------------------------

class TestAC6LineCountProxy:
    """AC6: mixin file must contain >= 1700 lines (builder confirmed 2554 moved)."""

    def test_mixin_line_count_at_least_1700(self):
        line_count = len(MIXIN_SRC.splitlines())
        assert line_count >= 1700, (
            f"track_modelling_ui.py has only {line_count} lines; "
            "expected >= 1700 (proxy for >= 2554 lines removed from dashboard.py)"
        )


# ---------------------------------------------------------------------------
# AC7 — zero self._db references in mixin
# ---------------------------------------------------------------------------

class TestAC7NoDbRefsInMixin:
    """AC7: track_modelling_ui.py must not reference self._db."""

    def test_no_self_db_in_mixin(self):
        hits = [(i + 1, ln.strip()) for i, ln in enumerate(MIXIN_SRC.splitlines())
                if "self._db" in ln]
        assert not hits, (
            f"self._db found in track_modelling_ui.py at lines: "
            + ", ".join(str(ln) for ln, _ in hits)
        )


# ---------------------------------------------------------------------------
# Ownership guards — attributes that must stay initialised in DashboardWindow
# ---------------------------------------------------------------------------

class TestOwnershipGuards:
    """Guard against state attributes being initialised inside the mixin,
    which would shadow the authoritative assignment in DashboardWindow.__init__."""

    def test_pit_lane_active_not_initialised_in_mixin(self):
        src = pathlib.Path(ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")
        # Mixin must not define __init__ — ownership of _pit_lane_active and
        # _tm_cached_draw_data initialisation belongs to DashboardWindow.__init__
        assert "def __init__" not in src, \
            "TrackModellingMixin must not define __init__; initial state attrs belong in DashboardWindow.__init__"

    def test_tm_cached_draw_data_initialised_in_dashboard(self):
        src = pathlib.Path(ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
        assert "self._tm_cached_draw_data" in src and "self._pit_lane_active" in src, \
            "_tm_cached_draw_data and _pit_lane_active must be initialised in dashboard.py"
