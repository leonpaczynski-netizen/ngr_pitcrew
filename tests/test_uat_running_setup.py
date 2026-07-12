"""Headless smoke test for the "Setup running this stint" flow (UAT #5).

Declared in the Live practice panel, carried into Practice Review (editable),
and passed to the AI with driver feedback (no schema change). Builds the real
MainWindow offscreen against an isolated temp config (config-safe pattern).

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
    cfg_path = str(tmp_path_factory.mktemp("running_setup") / "config.json")
    cp.write_default_config(cfg_path)
    config = cp.load_config(cfg_path)
    # Seed two saved setups so the running-setup combos have entries.
    config.setdefault("car_setup", {})["setups"] = [
        {"setup_label": "R Baseline 1", "setup_type": "Race",
         "name": "Porsche 911 RSR (991) '17", "track": "Fuji"},
        {"setup_label": "Q Baseline 1", "setup_type": "Qualifying",
         "name": "Porsche 911 RSR (991) '17", "track": "Fuji"},
    ]
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(
        config=config,
        logger=MagicMock(),
        announcer=MagicMock(),
        bridge=SignalBridge(),
        ui_queue=queue.Queue(),
        config_path=cfg_path,
        db=None,
    )
    yield win


def test_both_combos_exist_and_populated(window):
    assert hasattr(window, "_live_running_setup_combo")
    assert hasattr(window, "_prac_running_setup_combo")
    live_items = [window._live_running_setup_combo.itemText(i)
                  for i in range(window._live_running_setup_combo.count())]
    # Placeholder + the two seeded setups.
    assert live_items[0] == "— none —"
    assert "R Baseline 1 [Race]" in live_items
    assert "Q Baseline 1 [Qualifying]" in live_items


def test_declare_in_live_mirrors_to_practice(window):
    window._live_running_setup_combo.setCurrentText("R Baseline 1 [Race]")
    assert window._live_running_setup == "R Baseline 1 [Race]"
    # Practice Review combo mirrors the declared selection.
    assert window._prac_running_setup_combo.currentText() == "R Baseline 1 [Race]"


def test_edit_in_practice_updates_shared_state(window):
    window._prac_running_setup_combo.setCurrentText("Q Baseline 1 [Qualifying]")
    assert window._live_running_setup == "Q Baseline 1 [Qualifying]"
    assert window._live_running_setup_combo.currentText() == "Q Baseline 1 [Qualifying]"


def test_feedback_submit_passes_setup_to_ai(window):
    # Declare a running setup, then submit feedback with one field set.
    window._live_running_setup_combo.setCurrentText("R Baseline 1 [Race]")
    window._feedback_combos["Mid-Corner"].setCurrentText("Pushes wide")
    window._setup_feeling_input.setPlainText("")  # clear
    window._on_driver_feedback_submit()
    # The running setup must appear in the text handed to the setup-fix AI.
    feeling = window._setup_feeling_input.toPlainText()
    assert "Setup run this stint: R Baseline 1 [Race]" in feeling
    assert "Mid-Corner: Pushes wide" in feeling


def test_none_selection_omits_setup_line(window):
    window._prac_running_setup_combo.setCurrentText("— none —")
    assert window._live_running_setup == ""
    window._feedback_combos["Exit Stability"].setCurrentText("Poor traction")
    window._setup_feeling_input.setPlainText("")
    window._on_driver_feedback_submit()
    feeling = window._setup_feeling_input.toPlainText()
    assert "Setup run this stint" not in feeling
    assert "Exit Stability: Poor traction" in feeling
