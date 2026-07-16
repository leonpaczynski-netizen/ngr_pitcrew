"""Group 53 — live replan UI surface tests (source-verified).

The Strategy Builder Live Replan surface is verified by source inspection (no
QApplication constructed) — the known Win/Py3.14 PyQt cross-file segfault makes
constructing MainWindow in a shared test process unsafe. The dashboard's own
construction is covered separately by `test_ui_structure_smoke` (run individually).

All tests are pure/offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _dash():
    return ((ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8") + (ROOT / "ui" / "live_ui.py").read_text(encoding="utf-8") + (ROOT / "ui" / "race_plan_ui.py").read_text(encoding="utf-8"))


def _method(name: str) -> str:
    src = _dash()
    start = src.index(f"def {name}(self")
    end = src.index("\n    def ", start + 1)
    return src[start:end]


class TestSurfaceReadOnly:
    def test_refresh_button_exists(self):
        src = _dash()
        assert "Refresh Live Replan Snapshot" in src
        assert "_btn_rp_replan_refresh" in src
        assert "self._refresh_live_replan_snapshot" in src

    def test_refresh_method_reads_no_api_key(self):
        body = _method("_refresh_live_replan_snapshot")
        assert "api_key" not in body
        assert "_ai_api_key" not in body

    def test_refresh_method_no_apply_or_setup_history(self):
        body = _method("_refresh_live_replan_snapshot")
        for banned in ("setup_history", "_finalise_recommendation", "apply_ai_fields",
                       "save_entry", "insert_setup_recommendations", "_btn_apply"):
            assert banned not in body

    def test_refresh_method_shows_safety_and_missing(self):
        body = _method("_refresh_live_replan_snapshot")
        # advisory-only rendering via the pure renderer; missing state comes through it
        assert "render_live_replan_text" in body
        assert "build_live_replan_snapshot" in body

    def test_refresh_method_requires_pre_race_plan(self):
        body = _method("_refresh_live_replan_snapshot")
        assert "_last_race_plan_result" in body
        assert "Build a Race Plan first" in body


class TestNoAutoLoopOrVoice:
    def test_no_auto_refresh_timer_in_replan(self):
        body = _method("_refresh_live_replan_snapshot")
        for banned in ("QTimer", "singleShot", "start(", "while True"):
            assert banned not in body

    def test_no_voice_or_pit_call_path(self):
        body = _method("_refresh_live_replan_snapshot")
        for banned in ("announce", "VoiceAnnouncer", "speak", "pit_now", "send_command"):
            assert banned not in body

    def test_refresh_is_manual_click_only(self):
        src = _dash()
        # The button connects to the manual refresh; no timer drives it.
        assert "self._btn_rp_replan_refresh.clicked.connect(self._refresh_live_replan_snapshot)" in src


class TestRunPlanStoresResult:
    def test_run_race_plan_stores_pre_race_result(self):
        body = _method("_run_race_plan")
        assert "self._last_race_plan_result" in body
        assert "recommend_strategy_from_session" in body


class TestGroupBoxWording:
    def test_group_labelled_read_only_advisory(self):
        src = _dash()
        assert "Live Replan Readiness (read-only, advisory only)" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
