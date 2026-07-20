"""UAT Finding 1 — Applied setup automatically becomes the Live baseline.

Drives the REAL settings/Setup-Builder UI path: builds MainWindow offscreen,
clicks "Applied in Game" via the actual handler, and asserts the canonical
setup authority + Live baseline display update without any duplicate manual
selection. Complements the pure tests in test_group75_setup_state_authority.py.

Covers (through the real UI path): required tests 1, 3, 6-separation, 7.
"""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless UI test")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import config_paths as cp  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    cfg_path = str(tmp_path / "config.json")
    cp.write_default_config(cfg_path)
    config = cp.load_config(cfg_path)
    config.setdefault("strategy", {}).update({
        "car": "Porsche 911 RSR (991) '17",
        "track": "Fuji",
        "track_location_id": "fuji_international_speedway",
        "layout_id": "full_course",
    })
    config.setdefault("car_setup", {})["setups"] = [
        {"setup_label": "R Baseline 1", "setup_type": "Race",
         "setup_id": "1", "name": "Porsche 911 RSR (991) '17", "track": "Fuji"},
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
    win._query_listener = None
    yield win
    win.close()


def test_authority_constructed(window):
    assert getattr(window, "_setup_authority", None) is not None
    # Nothing applied yet -> no active setup, baseline label says so.
    ident = window._current_setup_identity()
    assert window._setup_authority.active_setup(ident, "Race") is None
    assert "none applied yet" in window._live_active_setup_lbl.text().lower()


def test_applied_in_game_sets_live_baseline(window):
    from data.setup_state_authority import SetupState
    form = window._race_form
    # Give the applied setup a recognisable name.
    try:
        form._setup_label.setText("R Baseline 1")
    except Exception:
        pass

    ident = window._current_setup_identity()
    assert ident.is_known, "event identity should resolve car+track from strategy"

    # Real handler — the "Applied in Game" button's slot.
    window._on_changes_applied_in_game(form)

    active = window._setup_authority.active_setup(ident, "Race")
    assert active is not None
    assert active.state is SetupState.APPLIED
    assert active.revision == 1
    # Complete snapshot captured (not just a couple of fields).
    assert len(active.fields) > 5

    # Live baseline display reflects it automatically — no manual reselection.
    text = window._live_active_setup_lbl.text()
    assert "Live baseline:" in text
    assert "rev 1" in text

    # The manual override combo was NOT touched by applying.
    assert window._live_running_setup_combo.currentText() == "— none —"
    assert window._live_running_setup == ""


def test_applied_setup_restores_after_restart(window, qapp):
    """The active setup persists to disk and a fresh authority restores it."""
    form = window._race_form
    try:
        form._setup_label.setText("R Baseline 1")
    except Exception:
        pass
    window._on_changes_applied_in_game(form)
    ident = window._current_setup_identity()

    # "Restart": rebuild the authority from the same on-disk store.
    from data.setup_state_authority import ActiveSetupAuthority
    from data.active_setup_store import JsonActiveSetupStore
    from pathlib import Path
    store_path = Path(window._config_path).with_name("active_setup_state.json")
    assert store_path.exists(), "applied setup should be persisted to disk"
    restored = ActiveSetupAuthority(store=JsonActiveSetupStore(store_path))
    active = restored.active_setup(ident, "Race")
    assert active is not None
    assert active.revision == 1


def test_apply_status_change_does_not_alter_snapshot(window):
    """Moving applied -> validation -> accepted preserves the snapshot/revision
    (required test 7), exercised via the window's authority."""
    from data.setup_state_authority import SetupState
    form = window._race_form
    window._on_changes_applied_in_game(form)
    ident = window._current_setup_identity()
    auth = window._setup_authority

    applied = auth.active_setup(ident, "Race")
    snap = dict(applied.fields)

    val = auth.start_validation(ident, "Race")
    assert val.state is SetupState.VALIDATION
    assert val.fields == snap and val.revision == applied.revision

    acc = auth.accept(ident, "Race")
    assert acc.state is SetupState.ACCEPTED
    assert acc.fields == snap and acc.revision == applied.revision
