"""Program 3 Phase E — live integration: _feed_live routes the engineer line through
the single Engineer Orchestrator (parity-preserving; the seam for the E machines).

Behavioural parity is covered by the existing suites (test_live_race_engineer_wiring
TestPracticeDoesNotLookLikeARace / TestTrackModellingSilencesLiveEngineer, and
test_live_engineer_session). This drift-guard pins the wiring itself so a future edit
can't quietly revert to the scattered direct call.
"""

import inspect

from ui.live_shell_bridge import LiveShellBridge


def test_feed_live_uses_the_orchestrator():
    src = inspect.getsource(LiveShellBridge._feed_live)
    assert "orchestrate(EngineerContext(" in src, "the engineer line must route through orchestrate()"
    # the scattered direct call is gone from the live path
    assert "session_engineer_call(" not in src


def test_orchestrator_line_parity_with_legacy():
    """The orchestrator reproduces the legacy line exactly when no richer state is
    supplied — which is what the live integration relies on for behaviour parity."""
    from strategy.engineer_orchestrator import EngineerContext, orchestrate
    from strategy.live_engineer_session import session_engineer_call, normalise_session_mode
    for mode, laps in [("practice", 0), ("practice", 2), ("practice", 5),
                       ("qualifying", 0), ("qualifying", 3), ("race", 4)]:
        legacy = session_engineer_call(
            normalise_session_mode(mode, ""), connected=True, lap_count=laps,
            last_lap_s=90.2, best_lap_s=90.0)
        got = orchestrate(EngineerContext(
            live_session_mode=mode, connected=True, lap_count=laps,
            last_lap_s=90.2, best_lap_s=90.0)).line
        assert got == legacy, f"{mode},{laps}: {got!r} != {legacy!r}"
