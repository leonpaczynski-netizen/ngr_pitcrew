"""The race news, through the controller: fed live, filed with its reasons.

The calls themselves are pinned in `test_race_news`. This pins the two roads
that make them real in a race: the pit wall's readings reach the race as they
are taken (not a lap late, at the crossing), and every call filed carries the
trigger and the model it was said on (§5.5).
"""
from __future__ import annotations

from pitcrew.race.calls import GAPS, STOPS_PICTURE, Call

from .test_controller import qt_app  # noqa: F401
from .test_race_wiring import green, raced, voice  # noqa: F401


def test_a_gap_reading_from_the_wall_reaches_the_race_as_it_is_taken(raced):
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    race = controller.race
    for _ in range(3):
        controller._on_wall_gap("ahead", 2.1, 7, "PUNISHED")
    assert race.news._neighbour["ahead"] == "PUNISHED"
    rows = [(1, "Rocky"), (2, "PUNISHED"), (3, "Beeni")]
    # With no place of our own read yet the board is refused, not guessed.
    race.state.position = None
    controller._on_wall_board(rows, 3)
    assert race.news._board is None
    race.state.position = 3
    controller._on_wall_board(rows, 3)
    assert race.news._board.places == {"Rocky": 1, "PUNISHED": 2, "Beeni": 3}


def test_a_volunteered_call_is_filed_with_why_it_was_said(raced):
    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    call = Call(GAPS, 3, "PUNISHED ahead, 2.1.", "",
                why_spoken="the car ahead is new; GT7's interval boxes as read")
    controller._on_position_changed(call)
    revisions = store.list_revisions(store.list_race_runs(event_id)[0]["id"])
    filed = [r for r in revisions if r["plan"].get("kind") == GAPS]
    assert filed and filed[-1]["plan"]["why_spoken"].startswith(
        "the car ahead is new")


def test_a_stop_picture_standing_in_for_a_place_brings_the_league_line(raced):
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    said = []
    controller.voice.say = lambda text, kind=None, on_done=None: said.append(
        text)
    controller._league_moved = lambda: "Up to championship P4."
    picture = Call(STOPS_PICTURE, 3, "P6 on the road.",
                   "Effectively P8 after the stops. If they stop once.",
                   position_called=6)
    controller._on_position_changed(picture)
    assert "Up to championship P4." in said
