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


class TestLiveRaceEngineerDisplay:
    """Asserts that set_state surfaces engineer_instruction, next_decision, and warning,
    and that show_plan renders a recommended replan candidate built via
    live_plan_dict_from_candidate.  These cover the live race engineer end-to-end
    display path without adding any command controls."""

    def test_engineer_instruction_rendered_prominently(self, qapp):
        w = LivePitWall()
        w.set_state(LivePitWallVM(
            engineer_instruction="Fuel is 0.3 L/lap over plan — lift and coast into the hairpin.",
            next_decision="Pit call on lap 22 — weather closing in",
            warning=(
                "Weather closing in — an extra stop for wets may be faster. "
                "Say 'accept plan' to switch, or 'keep plan' to stay out."),
            freshness="live", confidence="medium",
        ))
        # Text content is the authoritative check; isVisible() is unreliable in
        # headless test mode (parent window not shown) — use isHidden() for
        # explicit show/hide toggling, consistent with existing test conventions.
        assert "Fuel is 0.3 L/lap over plan" in w._instruction.text()
        assert w._instruction.text() != ""

    def test_next_decision_shown_when_present(self, qapp):
        w = LivePitWall()
        w.set_state(LivePitWallVM(next_decision="Pit call on lap 22 — weather closing in"))
        # setVisible(True) was called — use isHidden() (not isVisible()) in headless mode.
        assert not w._next.isHidden()
        assert "Pit call on lap 22" in w._next.text()

    def test_next_decision_hidden_when_blank(self, qapp):
        w = LivePitWall()
        w.set_state(LivePitWallVM(next_decision=""))
        assert not w._next.isVisible()

    def test_warning_visible_with_replan_cta(self, qapp):
        w = LivePitWall()
        w.set_state(LivePitWallVM(
            warning=(
                "Weather closing in — an extra stop for wets may be faster. "
                "Say 'accept plan' to switch, or 'keep plan' to stay out."),
        ))
        assert not w._warning.isHidden()
        assert "accept plan" in w._warning.text()
        assert "keep plan" in w._warning.text()

    def test_warning_hidden_when_blank(self, qapp):
        w = LivePitWall()
        w.set_state(LivePitWallVM(warning=""))
        assert w._warning.isHidden()

    def test_gap_to_plan_shows_pace_and_fuel_delta(self, qapp):
        w = LivePitWall()
        w.set_state(LivePitWallVM(gap_to_plan="+1.2s / +0.3 L per lap"))
        assert "+1.2s / +0.3 L per lap" in w._tiles["gap_to_plan"].text()

    def test_show_plan_from_candidate(self, qapp):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        plan = live_plan_dict_from_candidate({
            "label": "3-stop (Soft-Soft-Wet-Wet)",
            "stop_count_delta": 1,
            "expected_completed_laps": 34,
            "fuel_target_note": "Reduce to 28 L per stop — wets burn less",
            "tyre_note": "Switch to Wets from stop 2 once rain is confirmed",
            "expected_gain_detail": "Est. +18 s advantage on a wet track vs staying on Softs",
        })
        w = LivePitWall()
        w.show_plan(plan)
        assert not w._plan_card.isHidden()
        assert "3-stop" in w._plan_head.text()
        assert "Wets" in w._plan_stops.text()


class TestApprovedPlanDisplay:
    """UAT-8: "I approved race strategy and it took me to pit wall but nothing seems to
    be on it about the strategy." The approved plan is now shown (read-only)."""

    def test_show_plan_renders_the_approved_plan(self, qapp):
        from ui.components.live_pit_wall import LivePitWall
        w = LivePitWall()
        w.show_plan({"name": "Three-stop", "expected_laps": "62 laps",
                     "total_time": "2:08:24", "pit_windows": "3 stop(s)",
                     "pit_stops": ["Stop 1 (lap 16): leave with 55 L · ~35s · fit RH"]})
        assert w._plan_card.isHidden() is False
        assert "Three-stop" in w._plan_head.text() and "62 laps" in w._plan_head.text()
        assert "Stop 1" in w._plan_stops.text()

    def test_no_plan_hides_the_card(self, qapp):
        from ui.components.live_pit_wall import LivePitWall
        w = LivePitWall()
        w.show_plan({})
        assert w._plan_card.isHidden() is True
        w.show_plan("garbage")             # must not raise
        assert w._plan_card.isHidden() is True
