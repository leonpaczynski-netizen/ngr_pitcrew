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
from dataclasses import replace

from pitcrew.hub.read import Driver, Entry, Series
from pitcrew.hub.standings import Standing


class FakeHub:
    """A hub with two leagues, one car each."""

    available = True

    def __init__(self, *, same_car=False, no_driver=False, multi_class=False,
                 precomputed=None, entered=(), banned=()):
        self._no_driver = no_driver
        self._multi_class = multi_class
        self._precomputed = precomputed
        self._entered = list(entered)
        self._banned = set(banned)
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

    taken_at = None

    def close(self):
        pass

    def hidden_drivers(self):
        return self._banned

    def signed_in(self, series_id, on_or_after=None, already_run=(),
                  division_for_driver_id=None):
        return (list(self._entered), False)

    def precomputed_points(self, series_id):
        if self._precomputed is None:
            raise AssertionError("only a multi-class league asks for these")
        return dict(self._precomputed)

    def round_run_since(self, series_id, when):
        return False

    def driver_by_name(self, name):
        """Matches the way the real hub matches - case-folded, and on the PSN
        name too, which is the whole reason the canonical name must travel."""
        if self._no_driver:
            return None
        if str(name).strip().lower() in ("beeni", "beeni-187"):
            return Driver("me", "Beeni", "Beeni-187")
        return None

    def my_series(self, driver_id):
        fmt = "MULTI_CLASS_MANUFACTURER" if self._multi_class else None
        return [Series("gr3", "NGR GR3 Season 1", "ACTIVE", format=fmt,
                       pole_points=2, fastest_lap_points=1,
                       class_pole_points=2 if self._multi_class else 0,
                       class_fl_points=1 if self._multi_class else 0),
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
                rows.append({"id": f"{name}-{n}", "driverName": name,
                             "position": place, "status": "FINISHED",
                             "penalties": [], "roundId": f"r{n}"})
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


# --- the name we were given is not the name the table is keyed on ----------

def test_the_psn_name_finds_the_same_championship_as_the_board_name():
    """`driver_by_name` accepts either, so the caller cannot know which one it
    holds. The canonical name travels on the race and everything downstream
    uses it - compared raw, the lookup missed and the grid brief announced the
    championship won."""
    race = league_for(FakeHub(), {"series": "NGR GR3 Season 1"}, "Beeni-187")
    assert race.our_name == "Beeni"
    said = before_the_start(race, "Beeni-187").to_say()
    assert said and "Nobody left can catch you" not in said


# --- multi-class ------------------------------------------------------------

def test_a_multi_class_league_is_scored_from_the_hubs_own_totals():
    """A multi-class result is an overall finish PLUS a class one, which no
    finishing table expresses. The hub persists the sum and says every
    aggregation surface should prefer it verbatim."""
    hub = FakeHub(multi_class=True,
                  precomputed={f"{name}-{n}": 47
                               for name in ("Magical daddy", "Rocky", "Beeni",
                                            "Boxhead")
                               for n in range(1, 6)})
    race = league_for(hub, {"series": "NGR GR3 Season 1"}, "Beeni")
    assert race.known and not race.refused
    assert all(s.points == 47 * 5 for s in race.table)
    # 22 outright + 22 class + 2 class pole + 1 class fastest lap.
    assert race.per_race_max == 47


def test_a_multi_class_result_the_hub_has_not_computed_refuses_the_league():
    """All of them or none: one uncomputed result would fall through to the
    outright table and put two scales in one championship."""
    hub = FakeHub(multi_class=True, precomputed={"Beeni-1": 47})
    race = league_for(hub, {"series": "NGR GR3 Season 1"}, "Beeni")
    assert not race.known and "computed points" in race.refused


def test_a_multi_class_race_is_not_projected_from_the_board():
    """The board gives overall positions and says nothing about class, so the
    class half of the score is unknowable live. Crediting the outright half
    alone promoted this driver two places in the Enduro."""
    race = LeagueRace(series_id="x", series_name="X", rounds_left=1,
                      multi_class=True, our_name="Beeni",
                      table=[Standing("Rocky", 90), Standing("Beeni", 88)])
    assert project(race, "Beeni", 1) == []
    assert where_we_would_be(race, "Beeni", 1) is None


# --- who is actually here ---------------------------------------------------

def test_the_entry_list_narrows_the_rivals_when_the_board_has_seen_nobody():
    """On the grid the leaderboard reader has no frames and knows nobody, so
    the filter never ran and the driver was told to watch the top three of the
    whole championship."""
    hub = FakeHub(entered=["Rocky", "Beeni"])
    race = league_for(hub, {"series": "NGR GR3 Season 1"}, "Beeni")
    math = before_the_start(race, "Beeni")
    assert math.live_rivals == ["Rocky"]          # Magical daddy is not here
    assert math.rivals_from == "the entry list"


def test_the_board_outranks_the_entry_list_once_it_has_seen_anybody():
    hub = FakeHub(entered=["Rocky", "Beeni"])
    race = league_for(hub, {"series": "NGR GR3 Season 1"}, "Beeni")
    math = before_the_start(race, "Beeni", on_the_grid=["Magical daddy"])
    assert math.live_rivals == ["Magical daddy"]
    assert math.rivals_from == "the board"


def test_nothing_narrowing_the_list_is_marked_rather_than_guessed():
    """No sign-ins and no board is a real state - and an unnarrowed list must
    be marked as one so the caller does not read it as the field."""
    math = before_the_start(
        league_for(FakeHub(), {"series": "NGR GR3 Season 1"}, "Beeni"), "Beeni")
    assert math.live_rivals and math.rivals_from == ""


def test_a_banned_driver_never_reaches_the_table_or_the_entry_list():
    hub = FakeHub(banned={"rocky"}, entered=["Rocky", "Magical daddy"])
    race = league_for(hub, {"series": "NGR GR3 Season 1"}, "Beeni")
    assert not any(s.driver == "Rocky" for s in race.table)
    assert "Rocky" not in race.entered


# --- one ordering -----------------------------------------------------------

def test_the_projection_orders_the_table_the_way_the_table_orders_itself():
    """"Championship P4" on the grid and "championship 4 if it ends here"
    mid-race were computed by two different comparators. Under a helmet he
    cannot ask which one he just heard (rule 13)."""
    race = LeagueRace(series_id="x", series_name="X", rounds_left=1,
                      our_name="Beeni",
                      table=[Standing("Zed", 10), Standing("Alan", 10)])
    assert [s.driver for s in project(race, "Beeni", None)] == ["Alan", "Zed"]


# --- narrowing to nobody is not winning -------------------------------------

def test_narrowing_the_rivals_to_nobody_is_not_the_championship_won():
    """**The worst sentence this feature can say, by its second route.** The
    lookup failure was closed and this one was not: `to_say()` read ANY empty
    rival list as victory, and `before_the_start` overwrites the list with the
    narrowed set before it is called. A sign-in sheet that is still filling up,
    or a board of clusters nobody has labelled yet, told a driver forty-six
    points down that the championship was his."""
    hub = FakeHub(entered=["Beeni"])          # nobody else has signed in yet
    race = league_for(hub, {"series": "NGR GR3 Season 1"}, "Beeni")
    math = before_the_start(race, "Beeni")
    assert math.live_rivals == []             # narrowed away
    assert math.title_rivals                  # but they still exist
    assert not math.already_secured
    said = math.to_say()
    assert "Nobody left can catch you" not in said
    assert "No title rival is here." in said


def test_an_unlabelled_board_does_not_win_the_championship_either():
    """`_on_the_grid` passes provisional handles - "Car #1" - which match no
    hub name. That is the normal state of a cluster until it is named."""
    race = league_for(FakeHub(), {"series": "NGR GR3 Season 1"}, "Beeni")
    math = before_the_start(race, "Beeni",
                            on_the_grid=["Car #1", "Car #2", "Car #3"])
    assert math.live_rivals == [] and not math.already_secured
    assert "Nobody left can catch you" not in math.to_say()


def test_the_championship_really_being_won_still_says_so():
    """The good branch must survive the fix - it is decided by the UNNARROWED
    set, so who entered tonight cannot win or lose a title."""
    race = LeagueRace(series_id="x", series_name="X", rounds_left=0,
                      our_name="Beeni",
                      table=[Standing("Beeni", 95), Standing("Rocky", 20)])
    math = before_the_start(race, "Beeni", on_the_grid=["Nobody"])
    assert math.already_secured
    assert math.to_say() == "The championship is already yours."


def test_a_league_whose_class_table_will_not_parse_is_refused():
    """The overall scheme refuses loudly a few lines away; resolving a default
    for an unreadable CLASS table would quietly pay 22 for a class win in a
    league that may pay something else (rule 3)."""
    # Fully computed, so the league is refused for the SCHEME and not for
    # missing totals - the ceiling it sets decides who counts as a rival.
    hub = FakeHub(multi_class=True,
                  precomputed={f"{name}-{n}": 47
                               for name in ("Magical daddy", "Rocky", "Beeni",
                                            "Boxhead")
                               for n in range(1, 6)})
    race = league_for(_ClassSchemeUnreadable(hub),
                      {"series": "NGR GR3 Season 1"}, "Beeni")
    assert not race.known and "class points scheme" in race.refused


class _ClassSchemeUnreadable:
    """The hub, with one league's class table corrupted."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def my_series(self, driver_id):
        out = []
        for series in self._inner.my_series(driver_id):
            if series.id == "gr3":
                series = replace(series, class_points_scheme=None)
            out.append(series)
        return out
