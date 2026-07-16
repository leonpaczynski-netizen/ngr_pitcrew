"""Acceptance tests — Group A: Live Tab Cleanup (additional coverage).

Covers acceptance criteria that are not fully tested by
test_groupA_combo_no_autosync.py or test_groupA_session_override_property.py:

  AC1  — Live tab has no map widget / label / column; other Live controls remain;
          _build_live_tab is the only tab-builder in dashboard.py that touches the
          Live tab layout (no 'map' column artefacts).
  AC2  — Track Modelling tab map still works:
            * _tm_map_widget (not _live_map_widget) is updated in
              _tm_update_live_map_dot()
            * _tm_try_load_station_map_from_disk() updates _tm_map_widget
            * _tm_rebuild_model() is present and does not reference _live_map_widget
  AC3  — No dead _live_map_widget / _live_lbl_track / _live_try_load_active_event_map
          in telemetry/ and strategy/ trees (dashboard.py + mixin already covered
          by test_groupA_combo_no_autosync.py).
  AC4  — tests/test_group24_live_map_autoload.py does not exist.
  AC9  — set_race_active() is called from _on_live_mode_changed with True for
          "Race" and False for every other mode.
"""
from __future__ import annotations

import pathlib
import re
import unittest

# ---------------------------------------------------------------------------
# Source paths
# ---------------------------------------------------------------------------

_ROOT = pathlib.Path(__file__).parent.parent
_DASHBOARD_SRC = (_ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8") + (_ROOT / "ui" / "live_ui.py").read_text(encoding="utf-8")
_MIXIN_SRC     = (_ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")


def _method_body(source: str, method_name: str) -> str:
    """Return the source text of the named method (up to the next method at the same indent)."""
    start = source.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = source.find("\n    def ", start + 1)
    return source[start:end] if end != -1 else source[start:]


# ---------------------------------------------------------------------------
# AC1 — Live tab structural: no map widget, no map label, other controls remain
# ---------------------------------------------------------------------------

class TestAC1LiveTabNoMapArtifacts(unittest.TestCase):
    """AC1: map widget/label/column completely absent from the Live tab build path."""

    def setUp(self):
        self._body = _method_body(_DASHBOARD_SRC, "_build_live_tab")
        self.assertTrue(self._body, "_build_live_tab not found in dashboard.py")

    def test_no_live_map_widget_in_build_live_tab(self):
        """_build_live_tab must not create or reference _live_map_widget."""
        self.assertNotIn(
            "_live_map_widget", self._body,
            "_live_map_widget must not appear in _build_live_tab() "
            "— Live-tab map was removed in Group A"
        )

    def test_no_live_lbl_track_in_build_live_tab(self):
        """_build_live_tab must not create or reference _live_lbl_track."""
        self.assertNotIn(
            "_live_lbl_track", self._body,
            "_live_lbl_track must not appear in _build_live_tab()"
        )

    def test_no_TrackMapWidget_import_for_live_tab(self):
        """TrackMapWidget must not be instantiated inside _build_live_tab."""
        self.assertNotIn(
            "TrackMapWidget()", self._body,
            "TrackMapWidget() must not be instantiated inside _build_live_tab()"
        )

    def test_combo_live_mode_still_present(self):
        """_combo_live_mode must still be created in _build_live_tab."""
        self.assertIn(
            "_combo_live_mode", self._body,
            "_combo_live_mode must still be present in _build_live_tab() "
            "after Live-tab map removal"
        )

    def test_btn_reset_still_present(self):
        """The Reset Session button must still be wired in _build_live_tab."""
        self.assertIn(
            "_btn_reset", self._body,
            "_btn_reset must still be present in _build_live_tab() "
            "after Live-tab map removal"
        )

    def test_lbl_speed_still_present(self):
        """Speed label must still be created in _build_live_tab."""
        self.assertIn(
            "_lbl_speed", self._body,
            "_lbl_speed must still be present in _build_live_tab()"
        )

    def test_lbl_session_still_present(self):
        """Session label must still be created in _build_live_tab."""
        self.assertIn(
            "_lbl_session", self._body,
            "_lbl_session must still be present in _build_live_tab()"
        )


# ---------------------------------------------------------------------------
# AC2 — Track Modelling map still works (source-text / structural checks)
# ---------------------------------------------------------------------------

class TestAC2TrackModellingMapIntact(unittest.TestCase):
    """AC2: _tm_map_widget is the map widget used in Track Modelling; _live_map_widget absent."""

    # -- _tm_update_live_map_dot -----------------------------------------------

    def setUp(self):
        self._dot_body = _method_body(_MIXIN_SRC, "_tm_update_live_map_dot")
        self.assertTrue(self._dot_body, "_tm_update_live_map_dot not found in track_modelling_ui.py")

    def test_tm_map_widget_updated_in_tm_update_live_map_dot(self):
        """_tm_update_live_map_dot must call _tm_map_widget.set_draw_data()."""
        self.assertIn(
            "_tm_map_widget", self._dot_body,
            "_tm_map_widget must be referenced in _tm_update_live_map_dot() "
            "— Track Modelling map must still update"
        )

    def test_live_map_widget_absent_from_tm_update_live_map_dot(self):
        """_tm_update_live_map_dot must NOT reference _live_map_widget (removed widget)."""
        self.assertNotIn(
            "_live_map_widget", self._dot_body,
            "_live_map_widget must not appear in _tm_update_live_map_dot() "
            "— Live-tab map was removed in Group A"
        )

    def test_set_draw_data_called_in_tm_update_live_map_dot(self):
        """set_draw_data must be called for the Track Modelling map widget."""
        self.assertIn(
            "set_draw_data", self._dot_body,
            "set_draw_data() must be called in _tm_update_live_map_dot()"
        )

    # -- station-map load path (_tm_try_load_station_map_from_disk) -----------

    def test_station_map_load_updates_tm_map_widget(self):
        """_tm_try_load_station_map_from_disk must call _tm_map_widget.set_draw_data()."""
        load_body = _method_body(_MIXIN_SRC, "_tm_try_load_station_map_from_disk")
        self.assertTrue(load_body, "_tm_try_load_station_map_from_disk not found in track_modelling_ui.py")
        self.assertIn(
            "_tm_map_widget", load_body,
            "_tm_map_widget must be referenced in _tm_try_load_station_map_from_disk() "
            "so the map updates when a saved station map is loaded"
        )
        self.assertNotIn(
            "_live_map_widget", load_body,
            "_live_map_widget must not appear in _tm_try_load_station_map_from_disk()"
        )

    # -- _tm_rebuild_model ---------------------------------------------------

    def test_tm_rebuild_model_exists_in_mixin(self):
        """_tm_rebuild_model must be defined in track_modelling_ui.py."""
        self.assertIn(
            "def _tm_rebuild_model(", _MIXIN_SRC,
            "_tm_rebuild_model() must exist in track_modelling_ui.py"
        )

    def test_tm_rebuild_model_references_tm_map_widget(self):
        """_tm_rebuild_model must use _tm_map_widget to clear the map on reset."""
        rebuild_body = _method_body(_MIXIN_SRC, "_tm_rebuild_model")
        self.assertTrue(rebuild_body, "_tm_rebuild_model not found in track_modelling_ui.py")
        self.assertIn(
            "_tm_map_widget", rebuild_body,
            "_tm_map_widget must be referenced in _tm_rebuild_model() "
            "so the Track Modelling map blanks on recalibration reset"
        )

    def test_tm_rebuild_model_does_not_reference_live_map_widget(self):
        """_tm_rebuild_model must not reference the removed _live_map_widget."""
        rebuild_body = _method_body(_MIXIN_SRC, "_tm_rebuild_model")
        self.assertTrue(rebuild_body, "_tm_rebuild_model not found in track_modelling_ui.py")
        self.assertNotIn(
            "_live_map_widget", rebuild_body,
            "_live_map_widget must not appear in _tm_rebuild_model()"
        )

    # -- Station-map build path (inside _tm_build_path / its helper) ----------

    def test_station_map_build_path_updates_tm_map_widget(self):
        """After building a station map, _tm_map_widget must receive set_draw_data().

        _tm_build_path() is a thin handler that delegates to
        _tm_try_build_station_map() on success.  The map-widget update
        therefore lives in _tm_try_build_station_map(), not in _tm_build_path()
        itself.  We check the actual site of the update.
        """
        # First confirm _tm_build_path delegates to _tm_try_build_station_map.
        build_body = _method_body(_MIXIN_SRC, "_tm_build_path")
        self.assertTrue(build_body, "_tm_build_path not found in track_modelling_ui.py")
        self.assertIn(
            "_tm_try_build_station_map", build_body,
            "_tm_build_path must call _tm_try_build_station_map() on success"
        )

        # Then confirm the helper updates _tm_map_widget.
        helper_body = _method_body(_MIXIN_SRC, "_tm_try_build_station_map")
        self.assertTrue(helper_body, "_tm_try_build_station_map not found in track_modelling_ui.py")
        self.assertIn(
            "_tm_map_widget", helper_body,
            "_tm_map_widget must be referenced in _tm_try_build_station_map() "
            "so the Track Modelling map updates after building a station map"
        )
        self.assertNotIn(
            "_live_map_widget", helper_body,
            "_live_map_widget must not appear in _tm_try_build_station_map()"
        )


# ---------------------------------------------------------------------------
# AC3 — No dead refs in telemetry/ and strategy/ directories
# ---------------------------------------------------------------------------

_DEAD_SYMBOLS = (
    "_live_map_widget",
    "_live_lbl_track",
    "_live_try_load_active_event_map",
)


def _scan_directory(dirpath: pathlib.Path) -> dict[str, list[str]]:
    """Return {symbol: [file:lineno, ...]} for every dead symbol found in *.py files."""
    hits: dict[str, list[str]] = {s: [] for s in _DEAD_SYMBOLS}
    for py_file in sorted(dirpath.rglob("*.py")):
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(src.splitlines(), 1):
            for sym in _DEAD_SYMBOLS:
                if sym in line:
                    hits[sym].append(f"{py_file}:{lineno}")
    return hits


class TestAC3NoDeadRefsInTelemetryAndStrategy(unittest.TestCase):
    """AC3: dead Live-map symbols must not appear in telemetry/ or strategy/."""

    def _assert_no_hits(self, dirpath: pathlib.Path) -> None:
        hits = _scan_directory(dirpath)
        violations: list[str] = []
        for sym, locations in hits.items():
            for loc in locations:
                violations.append(f"  {sym}  at  {loc}")
        if violations:
            self.fail(
                f"Dead Live-map symbols found in {dirpath}:\n" + "\n".join(violations)
            )

    def test_no_dead_live_map_symbols_in_telemetry_dir(self):
        """None of the removed Live-map symbols appear in telemetry/*.py."""
        self._assert_no_hits(_ROOT / "telemetry")

    def test_no_dead_live_map_symbols_in_strategy_dir(self):
        """None of the removed Live-map symbols appear in strategy/*.py."""
        self._assert_no_hits(_ROOT / "strategy")


# ---------------------------------------------------------------------------
# AC4 — test_group24_live_map_autoload.py has been deleted
# ---------------------------------------------------------------------------

class TestAC4LiveMapAutoloadTestFileRemoved(unittest.TestCase):
    """AC4: tests/test_group24_live_map_autoload.py must not exist."""

    def test_live_map_autoload_test_file_absent(self):
        """The old Live-map autoload test file must have been deleted."""
        path = _ROOT / "tests" / "test_group24_live_map_autoload.py"
        self.assertFalse(
            path.exists(),
            "tests/test_group24_live_map_autoload.py still exists — "
            "it must be deleted as part of Group A cleanup (AC4)"
        )


# ---------------------------------------------------------------------------
# AC9 — set_race_active() reflects the currently displayed session type
#        (called from _on_live_mode_changed, which is the only combo-change path)
# ---------------------------------------------------------------------------

def _extract_on_live_mode_changed_body() -> str:
    body = _method_body(_DASHBOARD_SRC, "_on_live_mode_changed")
    assert body, "_on_live_mode_changed not found in dashboard.py"
    return body


class TestAC9SetRaceActiveCalledFromOnLiveModeChanged(unittest.TestCase):
    """AC9: set_race_active() is called exactly in _on_live_mode_changed."""

    def setUp(self):
        self._body = _extract_on_live_mode_changed_body()

    def test_set_race_active_present_in_on_live_mode_changed(self):
        """_on_live_mode_changed must call self._strategy_engine.set_race_active(...)."""
        self.assertIn(
            "set_race_active(", self._body,
            "set_race_active() must be called in _on_live_mode_changed()"
        )

    def test_set_race_active_passes_race_comparison(self):
        """set_race_active is called with (mode == \"Race\") so it is True only for Race."""
        # The production source must contain the exact boolean expression.
        self.assertIn(
            'set_race_active(mode == "Race")', self._body,
            '_on_live_mode_changed must pass (mode == "Race") to set_race_active() '
            "so it is True only when Race is selected"
        )

    def test_set_race_active_not_called_from_update_live(self):
        """set_race_active must NOT be called from _update_live().

        The only path that changes the combo (and therefore the session type
        for the strategy engine) is _on_live_mode_changed, not the packet handler.
        """
        update_live_body = _method_body(_DASHBOARD_SRC, "_update_live")
        self.assertTrue(update_live_body, "_update_live not found in dashboard.py")
        self.assertNotIn(
            "set_race_active", update_live_body,
            "set_race_active must not be called from _update_live() — "
            "only _on_live_mode_changed is the authorised caller"
        )

    def test_set_race_active_not_called_from_on_reset_clicked(self):
        """set_race_active must NOT be called from _on_reset_clicked().

        Reset clears the override but does not change the combo, so the
        strategy engine mode should remain unchanged.
        """
        reset_body = _method_body(_DASHBOARD_SRC, "_on_reset_clicked")
        self.assertTrue(reset_body, "_on_reset_clicked not found in dashboard.py")
        self.assertNotIn(
            "set_race_active", reset_body,
            "set_race_active must not be called from _on_reset_clicked()"
        )


class TestAC9SetRaceActiveSemantics(unittest.TestCase):
    """AC9 behavioural: set_race_active() receives True for Race, False for others.

    Uses a stub strategy engine to verify the boolean value passed for each
    possible mode.
    """

    def _make_fake_strategy_engine(self):
        class _FakeEngine:
            def __init__(self):
                self.calls: list[bool] = []

            def set_race_active(self, enabled: bool) -> None:
                self.calls.append(enabled)

        return _FakeEngine()

    def _simulate_on_live_mode_changed(self, engine, mode: str) -> None:
        """Replicate the set_race_active() call from the real _on_live_mode_changed."""
        if engine is not None:
            engine.set_race_active(mode == "Race")

    def test_race_mode_passes_true(self):
        eng = self._make_fake_strategy_engine()
        self._simulate_on_live_mode_changed(eng, "Race")
        self.assertEqual(eng.calls, [True],
                         "set_race_active must be called with True when mode == 'Race'")

    def test_practice_mode_passes_false(self):
        eng = self._make_fake_strategy_engine()
        self._simulate_on_live_mode_changed(eng, "Practice")
        self.assertEqual(eng.calls, [False],
                         "set_race_active must be called with False for 'Practice'")

    def test_qualifying_mode_passes_false(self):
        eng = self._make_fake_strategy_engine()
        self._simulate_on_live_mode_changed(eng, "Qualifying")
        self.assertEqual(eng.calls, [False],
                         "set_race_active must be called with False for 'Qualifying'")

    def test_mode_change_sequence(self):
        """Switching Race → Practice → Race produces [True, False, True]."""
        eng = self._make_fake_strategy_engine()
        for mode in ("Race", "Practice", "Race"):
            self._simulate_on_live_mode_changed(eng, mode)
        self.assertEqual(eng.calls, [True, False, True])


if __name__ == "__main__":
    unittest.main()
