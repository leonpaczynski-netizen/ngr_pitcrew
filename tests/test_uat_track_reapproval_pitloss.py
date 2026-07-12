"""UAT: track model must stay approved across restart; Strategy Builder pit loss
must reflect the persisted value (not 0). Headless MainWindow smoke tests.
Skipped when PyQt6 isn't importable.
"""
from __future__ import annotations

import os
import queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless smoke test")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import config_paths as cp  # noqa: E402
import data.track_model_alignment as tma  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _make_window(qapp, tmp_path, pit_loss=20.0):
    cfg_path = str(tmp_path / "config.json")
    cp.write_default_config(cfg_path)
    config = cp.load_config(cfg_path)
    config.setdefault("strategy", {})["pit_loss_secs"] = pit_loss
    from ui.dashboard import MainWindow, SignalBridge
    return MainWindow(
        config=config, logger=MagicMock(), announcer=MagicMock(),
        bridge=SignalBridge(), ui_queue=queue.Queue(), config_path=cfg_path, db=None,
    )


# ------------------------------------------------------ Bug D: pit loss seeded

def test_race_plan_pit_loss_seeded_from_config(qapp, tmp_path):
    win = _make_window(qapp, tmp_path, pit_loss=20.0)
    assert win._rp_pit_loss.value() == 20.0, "pit-loss field must seed from config, not 0"
    assert win._config_pit_loss_secs() == 20.0


def test_race_plan_pit_loss_resync_fills_zero(qapp, tmp_path):
    win = _make_window(qapp, tmp_path, pit_loss=18.5)
    win._rp_pit_loss.setValue(0.0)          # simulate a stale/unseeded 0
    win._sync_race_plan_pit_loss()
    assert win._rp_pit_loss.value() == 18.5
    # A deliberate override is preserved.
    win._rp_pit_loss.setValue(25.0)
    win._sync_race_plan_pit_loss()
    assert win._rp_pit_loss.value() == 25.0


# --------------------------------------------- Bug A: accepted model survives restart

def test_track_context_uses_disk_accepted_model_when_memory_none(qapp, tmp_path, monkeypatch):
    win = _make_window(qapp, tmp_path)
    # Simulate startup: no in-memory alignment yet.
    win._tm_alignment_result = None
    win._tm_seed_result = None
    win._tm_station_map = None
    win._tm_offset_calibration = None
    # Combos resolve a track/layout that has a persisted accepted model on disk.
    win._tm_location_combo = SimpleNamespace(currentData=lambda: "fuji")
    win._tm_layout_combo = SimpleNamespace(currentData=lambda: "fuji__full_course")

    accepted = SimpleNamespace(accepted=True, match_status="GOOD_MATCH")
    monkeypatch.setattr(tma, "find_accepted_model_path", lambda loc, lay: "on-disk-path")
    monkeypatch.setattr(tma, "import_accepted_model_json", lambda p: accepted)

    ctx = win._build_track_context()
    # The context must report the model as accepted from the disk fallback even
    # though the in-memory alignment was None (the every-launch re-approval bug).
    assert ctx.availability.accepted_model_available is True
