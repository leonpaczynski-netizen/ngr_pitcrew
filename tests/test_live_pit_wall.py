"""Tests for the Live Pit Wall (F6), including advisory-only safety."""

import inspect
import pytest

from PyQt6.QtWidgets import QApplication, QPushButton

from ui.components.live_pit_wall import LivePitWall, LivePitWallVM
import ui.components.live_pit_wall as live_mod


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _vm():
    return LivePitWallVM(
        lap="18 / 34", position="P4", stint="Stint 2 · L6", fuel="34 L (12 laps)",
        tyre="Soft · 62%", pit_window="L22–L25", gap_to_plan="+1.2s",
        engineer_instruction="Hold this pace — box in 4 laps for Mediums.",
        next_decision="Pit call on lap 22", warning="",
        freshness="live", confidence="high", map_trust="approved", ptt_status="RADIO READY")


class TestLivePitWall:
    def test_renders_kpis(self, qapp):
        w = LivePitWall()
        w.set_state(_vm())
        assert w._tiles["lap"].text() == "18 / 34"
        assert w._tiles["gap_to_plan"].text() == "+1.2s"
        assert "Hold this pace" in w._instruction.text()

    def test_freshness_and_map_trust_shown(self, qapp):
        w = LivePitWall()
        w.set_state(_vm())
        assert w._fresh.tone == "success"        # LIVE
        assert w._map_trust.tone == "success"    # approved reference path

    def test_low_confidence_fallback_looks_different(self, qapp):
        # A road-distance fallback must not read as a high-confidence match.
        w = LivePitWall()
        w.set_state(LivePitWallVM(map_trust="fallback", freshness="stale"))
        assert w._map_trust.tone == "warn"       # not success
        assert w._fresh.tone == "warn"           # STALE

    def test_warning_prominent_when_present(self, qapp):
        w = LivePitWall()
        w.set_state(LivePitWallVM(warning="Fuel critical — short-fill risk"))
        assert w._warning.isHidden() is False

    def test_empty_no_signal(self, qapp):
        w = LivePitWall()
        w.set_state(LivePitWallVM())
        assert w._fresh.tone == "neutral"        # NO SIGNAL
        assert w._tiles["lap"].text() == "—"

    def test_defensive(self, qapp):
        w = LivePitWall()
        w.set_state("garbage")
        assert w._tiles["lap"].text() == "—"


class TestLiveSafety:
    def test_no_command_buttons(self, qapp):
        # The live surface issues no pit/fuel/strategy command — it's advisory.
        w = LivePitWall()
        w.set_state(_vm())
        for btn in w.findChildren(QPushButton):
            text = (btn.text() or "").lower()
            assert not any(tok in text for tok in ("pit now", "box now", "apply", "execute")), \
                f"unexpected command control: {btn.text()!r}"

    def test_source_has_no_command_tokens(self):
        src = inspect.getsource(live_mod).lower()
        for tok in ("set_plan(", "apply(", "make_pit", "execute_pit", "strategy_engine"):
            assert tok not in src
