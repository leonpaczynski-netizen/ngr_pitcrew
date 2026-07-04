"""Headless UI structure smoke test — post-UAT clarity overhaul.

Builds the real MainWindow offscreen against an isolated temp config (the same
config-safe pattern as test_config_safety_smoke.py) and asserts the structural
outcomes of the overhaul actually materialise in the live widget tree:

  * 13 tabs (the Guide tab was folded into Home),
  * no "Guide" tab remains,
  * the core workflow tabs are present,
  * Setup Builder holds two SetupFormWidget panels (Race + Qualifying),
  * the Track Model Status panel has its "Next step" label,
  * the per-tab guidance-header helper and the folded guide widget exist.

Skipped when PyQt6 isn't importable so pure-Python CI still passes.
"""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless smoke test")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import config_paths as cp  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="module")
def window(qapp, tmp_path_factory):
    """Construct MainWindow once, offscreen, against an isolated temp config."""
    cfg_path = str(tmp_path_factory.mktemp("ui_smoke") / "config.json")
    cp.write_default_config(cfg_path)
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(
        config=cp.load_config(cfg_path),
        logger=MagicMock(),
        announcer=MagicMock(),
        bridge=SignalBridge(),
        ui_queue=queue.Queue(),
        config_path=cfg_path,
        db=None,
    )
    yield win


def _titles(win) -> list[str]:
    return [win._tabs.tabText(i) for i in range(win._tabs.count())]


def test_thirteen_tabs(window):
    assert window._tabs.count() == 13


def test_no_guide_tab(window):
    for title in _titles(window):
        assert "Guide" not in title, f"Guide tab should be removed, found: {title!r}"


def test_core_workflow_tabs_present(window):
    joined = " | ".join(_titles(window))
    for name in ("Home", "Live Race Engineer", "Event Planner", "Garage",
                 "Setup Builder", "Practice Review", "Strategy Builder"):
        assert name in joined, f"missing workflow tab: {name}"


def test_home_is_first_tab(window):
    assert _titles(window)[0] == "Home"


def test_setup_builder_has_two_side_by_side_forms(window):
    from ui.setup_form_widget import SetupFormWidget
    assert isinstance(window._race_form, SetupFormWidget)
    assert isinstance(window._qual_form, SetupFormWidget)
    assert window._race_form.purpose == "Race"
    assert window._qual_form.purpose == "Qualifying"
    # Distinct instances — not the same panel reused.
    assert window._race_form is not window._qual_form


def test_live_session_mode_toggle_preserved(window):
    # self._setup_type must survive the side-by-side refactor: main.py's on_packet
    # reads it (via _practice_is_qual_ref) to pick the shift-RPM threshold.
    assert hasattr(window, "_setup_type")
    assert window._setup_type.count() == 2  # Race Setup / Qualifying Setup


def test_track_model_next_step_label_present(window):
    assert hasattr(window, "_tm_rs_next_step")


def test_guidance_helpers_exist(window):
    # Per-tab header helper + the folded-in guide reference widget.
    assert callable(getattr(window, "_tab_intro_header", None))
    assert callable(getattr(window, "_build_guide_reference_widget", None))
