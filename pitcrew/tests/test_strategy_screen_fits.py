"""The plans have to fit on the screen they are drawn on.

*"you can't see the plans formatting is corrupt, formatting on all screens
seems off horizontally"*

The window-geometry fix was necessary and not sufficient. Every screen was
measured **empty**, which is the state none of them are in when he is looking
at one. Loaded with a real plan, Strategy demanded 6,268 px of width — four
times the widest monitor on the rig — because the evidence notes are prose and
the label they were drawn in refused to wrap. The plan rendered perfectly and
every column of it was off the side of the screen.
"""
from __future__ import annotations

from pitcrew.strategy.evidence import ASSUMED, DECLARED, MEASURED, Evidence
from pitcrew.ui.strategy_screen import StrategyScreen

from .test_controller import qt_app  # noqa: F401


# The real one from the Monza plan: measured off the game clock, and long.
LONG_NOTE = (
    "Measured over 40 laps: the game clock runs at x6 from 15:56 and stops at "
    "18:50 - this circuit has no 24-hour cycle, so its clock holds there "
    "rather than running into the next morning, and no race here can cover "
    "conditions past it. Practice was not run at the race's clock: 1 of 3 "
    "practice sessions ran with the clock frozen, so they sat at one hour and "
    "say nothing about a race that moves through several.")


def some_evidence() -> list[Evidence]:
    return [
        Evidence("Reference lap", "1:47.982", MEASURED, "fastest counted lap"),
        Evidence("Time of day", "15:56-18:50", ASSUMED, LONG_NOTE),
        Evidence("Refuel rate", "1.00 L/s", DECLARED, LONG_NOTE),
    ]


def test_a_paragraph_of_evidence_does_not_set_the_window_width(qt_app):
    screen = StrategyScreen()
    screen.show_plans([], some_evidence())
    assert screen.minimumSizeHint().width() < 900, (
        "an unwrapped note makes its longest sentence the minimum width")


def test_the_empty_state_is_hidden_once_there_are_plans(qt_app):
    """Taking it out of the layout does not take it off the screen. It stays
    a child of the holder, keeps its last geometry, and draws underneath the
    cards — which put "a tyre-gauge reading, for the wear rate" through the
    middle of the fastest strategy."""
    screen = StrategyScreen()
    screen.show_plans([], some_evidence())
    assert screen.plan_empty.isVisibleTo(screen) is True

    screen.show_plans([_a_plan()], some_evidence())
    assert screen.plan_empty.isVisibleTo(screen) is False

    screen.show_plans([], some_evidence())
    assert screen.plan_empty.isVisibleTo(screen) is True, (
        "a rebuild that produces nothing has to say so again")


def _a_plan():
    from pitcrew.strategy.model import Plan, Stint
    return Plan(
        stints=[Stint(laps=14, compound="RH", fuel_l=92.4, start_lap=1),
                Stint(laps=13, compound="RH", fuel_l=86.2, start_lap=15)],
        total_time_s=3030.9, binding_constraint="tyre", notes=[],
        delta_s=0.0, feasible=True, profiles={}, crossover=None)
