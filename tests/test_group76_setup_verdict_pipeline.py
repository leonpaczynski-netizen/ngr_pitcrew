"""Holistic brain — Phase 3 pipeline + UI render."""
from __future__ import annotations

import os
import queue
import types
from unittest.mock import MagicMock

import pytest

from strategy.setup_verdict_pipeline import build_verdict_from_laps
from strategy.setup_session_verdict import SetupOverall


SEGS = [
    types.SimpleNamespace(segment_id="t1_apex", turn_number=1, display_name="Turn 1"),
    types.SimpleNamespace(segment_id="t4_apex", turn_number=4, display_name="Turn 4"),
]


def _resolver(frame):
    return frame.get("_seg", ""), ""


def _lap(setup_id, lap_ms, t1_apex, t4_apex, spin=1, pit=False):
    return {
        "setup_id": setup_id, "lap_time_ms": lap_ms, "is_pit_lap": pit,
        "wheelspin_count": spin, "lock_up_count": 1,
        "frames": [
            {"road_distance": 100, "speed_kmh": t1_apex, "throttle": 0.0,
             "brake": 0.1, "gear": 3, "_seg": "t1_apex"},
            {"road_distance": 400, "speed_kmh": t4_apex, "throttle": 0.9,
             "brake": 0.0, "gear": 4, "_seg": "t4_apex"},
        ],
    }


def test_pipeline_compares_two_setups():
    # Newest-first: setup 2 (newer) then setup 1 (older).
    laps = [
        _lap(2, 89700, t1_apex=118, t4_apex=101, spin=1),
        _lap(2, 89800, t1_apex=119, t4_apex=100, spin=1),
        _lap(2, 89900, t1_apex=118, t4_apex=101, spin=1),
        _lap(1, 90000, t1_apex=120, t4_apex=95, spin=2),
        _lap(1, 90100, t1_apex=121, t4_apex=95, spin=2),
        _lap(1, 90050, t1_apex=120, t4_apex=94, spin=2),
    ]
    v = build_verdict_from_laps(
        laps, _resolver, SEGS, labels={1: "R rev1", 2: "R rev2"},
        changes=[{"setting": "Rear ARB", "from": 5, "to": 4}],
        feedback_vs_previous="better")
    assert v is not None
    assert v.cur_label == "R rev2" and v.prev_label == "R rev1"
    assert v.overall is SetupOverall.IMPROVED       # ~ -0.3s best
    assert "Turn 4" in {c.corner_name for c in v.better_corners}
    assert any("wheelspin down" in r.lower() for r in v.reasons)


def test_pipeline_needs_two_setups():
    laps = [_lap(1, 90000, 120, 95), _lap(1, 90100, 120, 95)]
    assert build_verdict_from_laps(laps, _resolver, SEGS) is None


# --------------------------------------------------------------------------- #
# UI render through the real panel (module-scoped fixtures = stable teardown)
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    import config_paths as cp
    cfg = str(tmp_path / "config.json")
    cp.write_default_config(cfg)
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(config=cp.load_config(cfg), logger=MagicMock(),
                     announcer=MagicMock(), bridge=SignalBridge(),
                     ui_queue=queue.Queue(), config_path=cfg, db=None)
    win._query_listener = None
    yield win
    win.close()


def test_verdict_ui_render(window):
    assert hasattr(window, "_btn_setup_verdict")
    laps = [
        _lap(2, 89700, 118, 101), _lap(2, 89800, 119, 100), _lap(2, 89900, 118, 101),
        _lap(1, 90000, 120, 95), _lap(1, 90100, 121, 95), _lap(1, 90050, 120, 94),
    ]
    v = build_verdict_from_laps(laps, _resolver, SEGS,
                                labels={1: "R rev1", 2: "R rev2"})
    window._render_setup_verdict(v)
    assert not window._verdict_reasons_list.isHidden()
    assert window._verdict_reasons_list.count() >= 1
    assert "improved" in window._verdict_summary_lbl.text().lower()
    # Empty-safe.
    window._render_setup_verdict(None)
    assert window._verdict_reasons_list.isHidden()
