"""Tying a race to its championship, and keeping it live.

A race matched to the WRONG league computes a title from somebody else's
points, so most of this is about the matcher refusing rather than guessing.
"""
from __future__ import annotations

import pytest

from pitcrew.hub.link import (
    LeagueRace,
    _same_car,
    before_the_start,
    league_for,
    project,
    where_we_would_be,
)
from pitcrew.hub.read import Driver, Entry, Series
from pitcrew.hub.standings import Standing


class FakeHub:
    """A hub with two leagues, one car each."""

    available = True

    def __init__(self, *, same_car=False, no_driver=False):
        self._no_driver = no_driver
        second = "Lamborghini Huracan GT3 '15" if same_car \
            else "Ford Shelby GT350R '16"
        self._entries = {
            "gr3": [Entry("gr3", "me", "Beeni", "Lamborghini Huracan GT3 '15",
                          "BeenHead"),
                    Entry("gr3", "box", "Boxhead", None, "BeenHead")],
            "sc": [Entry("sc", "me", "Beeni", second, "V-Monster")],
        }

    def freshness(self):
        return "hub from today"

    stale = False

    def driver_by_name(self, name):
        return None if self._no_driver else Driver("me", "Beeni", "Beeni-187")

    def my_series(self, driver_id):
        return [Series("gr3", "NGR GR3 Season 1", "ACTIVE", pole_points=2,
                       fastest_lap_points=1),
                Series("sc", "NGR Supercars Series 1", "ACTIVE")]

    def entries(self, series_id):
        return self._entries.get(series_id, [])

    def teammates(self, series_id, driver_id):
        return ["Boxhead"] if series_id == "gr3" else []

    def rounds(self, series_id):
        return [{"id": f"r{n}"} for n in range(1, 9)]

    def results(self, series_id):
        rows = []
        for n in range(1, 6):
            for name, place in (("Magical daddy", 1), ("Rocky", 2),
                                ("Beeni", 4), ("Boxhead", 6)):
                rows.append({"driverName": name, "position": place,
                             "status": "FINISHED", "penalties": [],
                             "roundId": f"r{n}"})
        return rows


# --- matching --------------------------------------------------------------

def test_the_event_naming_its_league_is_believed_first():
    race = league_for(FakeHub(), {"series": "NGR Supercars Series 1"}, "Beeni")
    assert race.series_name == "NGR Supercars Series 1"
    assert race.matched_by == "the event names it"


def test_the_car_identifies_the_league_when_the_event_does_not():
    race = league_for(FakeHub(),
                      {"car_name": "Lamborghini Huracan GT3 '15"}, "Beeni")
    assert race.series_name == "NGR GR3 Season 1"
    assert race.matched_by == "the car"


def test_one_car_in_two_leagues_is_not_a_match():
    """Two leagues in one car is a coin toss, and a title computed from the
    wrong one is worse than none."""
    race = league_for(FakeHub(same_car=True),
                      {"car_name": "Lamborghini Huracan GT3 '15"}, "Beeni")
    assert not race.known and race.matched_by == "nothing"


def test_a_car_in_no_league_matches_nothing():
    race = league_for(FakeHub(), {"car_name": "Mazda Demio"}, "Beeni")
    assert not race.known


def test_a_driver_the_hub_does_not_know_gets_no_league():
    race = league_for(FakeHub(no_driver=True),
                      {"car_name": "Lamborghini Huracan GT3 '15"}, "Beeni")
    assert not race.known


def test_car_names_are_compared_loosely_but_not_carelessly():
    """Two applications maintained apart. Case and punctuation are dropped;
    the accented letter is not, because dropping it would make two different
    cars compare equal more often than it would rescue a mismatch."""
    assert _same_car("Ford Shelby GT350R '16", "ford shelby gt350r 16")
    assert not _same_car("Porsche 911 RSR (991) '17",
                         "Porsche 911 GT3 R (992) '22")
    assert not _same_car(None, "anything")


# --- the grid --------------------------------------------------------------

def test_the_grid_line_names_the_rivals_who_are_actually_here():
    race = league_for(FakeHub(),
                      {"car_name": "Lamborghini Huracan GT3 '15"}, "Beeni")
    math = before_the_start(race, "Beeni",
                            on_the_grid=["Rocky", "Boxhead", "Nobody"])
    assert set(math.live_rivals) <= {"Rocky", "Boxhead"}
    assert math.to_say()


def test_no_league_means_no_grid_line_rather_than_an_empty_one():
    assert before_the_start(LeagueRace(), "Beeni") is None


def test_the_teammate_comes_from_the_hub_not_from_a_setting():
    race = league_for(FakeHub(),
                      {"car_name": "Lamborghini Huracan GT3 '15"}, "Beeni")
    assert race.teammates == ["Boxhead"]


# --- the live projection ---------------------------------------------------

def a_race():
    return LeagueRace(series_id="x", series_name="X", rounds_left=2,
                      table=[Standing("Magical daddy", 95),
                             Standing("Rocky", 90),
                             Standing("Beeni", 68)])


def a_close_race():
    """A table near enough that one result moves it. The 27-point gap in
    `a_race()` does NOT close in a single round, which is the correct answer
    there and the wrong fixture for this question."""
    return LeagueRace(series_id="x", series_name="X", rounds_left=2,
                      table=[Standing("Magical daddy", 95),
                             Standing("Rocky", 90),
                             Standing("Beeni", 88)])


def test_a_better_finish_moves_us_up_the_projected_table():
    high = where_we_would_be(a_close_race(), "Beeni", 1,
                             {"Magical daddy": 8, "Rocky": 9})
    low = where_we_would_be(a_close_race(), "Beeni", 12,
                            {"Magical daddy": 1, "Rocky": 2})
    assert high == 1 and low == 3


def test_a_gap_too_big_to_close_in_one_round_does_not_move():
    """Winning from 27 behind with one round counted is still third, and
    saying otherwise would be the projection flattering him."""
    assert where_we_would_be(a_race(), "Beeni", 1,
                             {"Magical daddy": 8, "Rocky": 9}) == 3


def test_a_driver_off_the_board_keeps_his_points_rather_than_gaining_any():
    """The board shows eight. A rival further back is projected on what he
    already has - which understates him, and that is the safe direction: it
    can miss a threat but never invent one."""
    projected = project(a_race(), "Beeni", 3, {"Rocky": 1})
    magical = next(s for s in projected if s.driver == "Magical daddy")
    assert magical.points == 95        # unchanged, he was not on the board


def test_the_projection_is_empty_without_a_league():
    assert project(LeagueRace(), "Beeni", 1) == []
    assert where_we_would_be(LeagueRace(), "Beeni", 1) is None


def test_no_position_of_our_own_still_projects_the_rivals():
    projected = project(a_race(), "Beeni", None, {"Rocky": 1})
    rocky = next(s for s in projected if s.driver == "Rocky")
    us = next(s for s in projected if s.driver == "Beeni")
    assert rocky.points == 90 + 22 and us.points == 68
