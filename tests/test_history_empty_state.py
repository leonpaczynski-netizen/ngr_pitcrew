"""Driver-facing empty state on the History tab (UI Pass 5).

Builds the real MainWindow offscreen against an isolated temp config + an empty
(but real) SessionDB, and asserts the History tab shows a helpful "what to do
next" message instead of a silent blank table. Also exercises the direct
toggle helper for the hide/other-message branches without a second window.

Skipped when PyQt6 isn't importable so pure-Python CI still passes.
"""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless test")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import config_paths as cp  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(qapp, tmp_path_factory):
    d = tmp_path_factory.mktemp("hist_empty")
    cfg_path = str(d / "config.json")
    cp.write_default_config(cfg_path)
    from data.session_db import SessionDB
    db = SessionDB(str(d / "empty.db"))  # real DB, zero sessions
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(
        config=cp.load_config(cfg_path),
        logger=MagicMock(),
        announcer=MagicMock(),
        bridge=SignalBridge(),
        ui_queue=queue.Queue(),
        config_path=cfg_path,
        db=db,
    )
    yield win
    db.close()


def test_empty_history_shows_actionable_message(window):
    window._refresh_history()
    assert window._hist_empty_lbl.isHidden() is False
    txt = window._hist_empty_lbl.text().lower()
    # Confident, driver-facing, tells the user exactly what to do next.
    assert "no saved sessions yet" in txt
    assert "record" in txt or "recorded" in txt
    # Never the vague forbidden copy.
    assert txt not in ("no data", "error", "unknown", "")


def test_empty_state_helper_hides_on_none(window):
    window._set_history_empty_state("something")
    assert window._hist_empty_lbl.isHidden() is False
    window._set_history_empty_state(None)
    assert window._hist_empty_lbl.isHidden() is True


def test_db_unavailable_message(window):
    # Temporarily drop the DB reference to exercise the unavailable branch.
    _saved = window._db
    try:
        window._db = None
        window._refresh_history()
        assert window._hist_empty_lbl.isHidden() is False
        assert "unavailable" in window._hist_empty_lbl.text().lower()
    finally:
        window._db = _saved
        window._refresh_history()  # restore populated/empty state cleanly
