"""Program 3 Phase D3 — atomic/complete event-switch reset.

Switching, creating or finishing an event must clear EVERY per-event / per-run
cache through one shared method, so a page can never render the previous event's
data and a newly-added cache can't be forgotten in one of the three handlers.
"""

import inspect
import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.live_shell_bridge import LiveShellBridge
from ui.pit_crew_controller import PitCrewController
from ui.pit_crew_shell import PitCrewShell


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_reset_clears_every_context_cache(qapp):
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    b = LiveShellBridge(shell, ctrl, window=None, config={"strategy": {}})
    # dirty every per-event / per-run cache
    b._review_cache["s"] = object()
    b._runs_cache = [1]
    b._run_discipline = {1: "race"}
    b._lock_report = object()
    b._last_analysis = object()
    b._live_accepted_plan = object()
    b._live_audio_view = object()
    b._live_decision_lap = 5
    b._live_decision = object()
    b._live_pending = True
    b._last_guidance_view = object()
    b._last_engine_plan_key = "k"
    b._test_compound_override = "RH"
    b._last_compound_codes = ("RH",)

    b._reset_context_caches()

    assert b._review_cache == {}
    assert b._runs_cache is None
    assert b._run_discipline == {}
    assert b._lock_report is None
    assert b._last_analysis is None
    assert b._live_accepted_plan is None
    assert b._live_audio_view is None
    assert b._live_decision_lap is None
    assert b._live_decision is None
    assert b._live_pending is False
    assert b._last_guidance_view is None
    assert b._last_engine_plan_key == ""
    assert b._test_compound_override is None
    assert b._last_compound_codes == ()


def test_per_cycle_caches_are_covered(qapp):
    """The old inline block missed _runs_cache / _run_discipline / _lock_report,
    which could show the previous event's runs/lock on the first post-switch tick."""
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    b = LiveShellBridge(shell, ctrl, window=None, config={"strategy": {}})
    b._runs_cache = ["prev-event-run"]
    b._lock_report = "prev-event-lock"
    b._reset_context_caches()
    assert b._runs_cache is None
    assert b._lock_report is None


def test_all_switch_and_finish_handlers_use_the_shared_reset():
    """Drift guard: the three handlers must route through _reset_context_caches so a
    future cache addition is handled in exactly one place."""
    for name in ("_on_activate_event", "_on_event_draft_saved", "_finish_active_event"):
        src = inspect.getsource(getattr(LiveShellBridge, name))
        assert "_reset_context_caches()" in src, f"{name} must use the shared reset"
