"""The race's record of rival stops: retired when said, or when stale, only.

Bathurst, 14 Sep 2026: the entries were a queue drained at every crossing,
and box calls won the crossings - eight of ten stops were never said.
"""
from __future__ import annotations

from pitcrew.race.calls import (BOX_NOW, RIVAL_BOXED, Call, RaceState,
                                next_call)
from pitcrew.race.lane import STALE_AFTER_LAPS, LaneLog
from pitcrew.race.pit_wall import Entered
from pitcrew.race.rival_calls import BOXED_NAMES, boxed_call


def entered(driver, lap=9, fuel=20, partial=False, ahead=None):
    return Entered(driver=driver, driver_id=0, lap=lap, fuel_in_l=fuel,
                   partial=partial, ahead_at_entry=ahead)


def test_offered_is_not_said():
    """A crossing a box call won must not cost the stop."""
    state = RaceState(lap=9, laps_total=20)
    state.lane.enter(entered("PUNISHED"), lap=9)
    assert boxed_call(state) is not None          # offered at lap 9...
    state.record(Call(BOX_NOW, 10, "Box this lap.", ""))   # ...a box call won
    state.lap = 10
    call = next_call(state)
    assert call.kind == RIVAL_BOXED and "PUNISHED" in call.call


def test_said_is_retired_and_only_the_stops_it_named():
    state = RaceState(lap=9, laps_total=20)
    state.lane.enter(entered("PUNISHED"), lap=9)
    call = boxed_call(state)
    state.lane.enter(entered("K.Graebs"), lap=9)   # arrives after it was built
    state.record(call)
    assert [s.driver for s in state.lane.untold(9)] == ["K.Graebs"]


def test_a_stop_goes_stale_a_full_lap_after_he_left():
    lane = LaneLog()
    lane.enter(entered("TommyTbone", lap=12), lap=12)
    lane.left("TommyTbone", lap=12)                # filed while driving lap 13
    assert lane.untold(13)                         # the crossing ending lap 13
    assert lane.untold(14) == []                   # a lap later: history


def test_a_stop_never_filed_goes_stale_on_its_own_clock():
    lane = LaneLog()
    lane.enter(entered("Car #30", lap=8), lap=8)
    assert lane.untold(8 + STALE_AFTER_LAPS - 1)
    assert lane.untold(8 + STALE_AFTER_LAPS) == []


def test_the_same_visit_is_on_file_once():
    lane = LaneLog()
    assert lane.enter(entered("PUNISHED"), lap=9) is not None
    assert lane.enter(entered("PUNISHED"), lap=9) is None
    # A second stop is a second visit.
    assert lane.enter(entered("PUNISHED", lap=15), lap=15) is not None


def test_a_new_session_forgets_everything():
    """Rule 11: a stop is news about one race."""
    lane = LaneLog()
    lane.enter(entered("PUNISHED", ahead=True), lap=9)
    lane.explain([s.key for s in lane.passed_in_the_lane()])
    lane.new_session()
    assert lane.untold(9) == [] and lane.in_the_lane() == []


def test_arming_empties_the_record():
    from pitcrew.race.coordinator import RaceCoordinator

    co = RaceCoordinator()
    co.state.lane.enter(entered("PUNISHED"), lap=9)
    co.arm(None, None)
    assert co.state.lane.untold(9) == []


def test_several_stops_are_one_sentence_and_the_rest_are_counted():
    state = RaceState(lap=11, laps_total=20)
    names = ["PUNISHED", "CruisingChaos", "K.Graebs", "Magical daddy", "Car #31"]
    for name in names:
        state.lane.enter(entered(name), lap=11)
    call = boxed_call(state)
    assert call.call == "PUNISHED, CruisingChaos, K.Graebs and 2 more have boxed."
    assert len(state.lane.keys_in_tag(RIVAL_BOXED, call.tag)) == len(names)
    assert BOXED_NAMES == 3


def test_a_watched_rival_leads_and_is_never_one_of_the_more():
    state = RaceState(lap=11, laps_total=20)
    state.watched_rivals = frozenset({"car #31"})
    for name in ["PUNISHED", "CruisingChaos", "K.Graebs", "Magical daddy",
                 "Car #31"]:
        state.lane.enter(entered(name), lap=11)
    call = boxed_call(state)
    assert call.call.startswith("Car #31, PUNISHED, CruisingChaos and 2 more")
    assert call.severity and call.severity > 0


def test_a_name_with_the_separator_still_splits_back():
    lane = LaneLog()
    stop = lane.enter(entered("A|B"), lap=3)
    tag = lane.tag_for(RIVAL_BOXED, [stop])
    assert lane.keys_in_tag(RIVAL_BOXED, tag) == [stop.key]
