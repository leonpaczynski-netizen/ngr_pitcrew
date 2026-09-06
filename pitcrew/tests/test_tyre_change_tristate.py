"""A tyre change is seen, or unknown - never "no" because nothing looked.

Deep Forest, 6 Sep 2026, lap 13. The swap detector - all four corners stepping
down in one frame at walking pace - did not fire on a stop that fitted a fresh
set; PIT_EXIT then emitted `bool(None)` = False, the coordinator kept the old
set's wear history, the live fit ran through 0.42 -> 0.00 -> 0.03 and the
briefed projection counted thirteen laps on a one-lap-old set. The gauge had
read the fresh set the whole time and nothing asked it.

Four things, all here: the session emits True or None, never a default False;
`clear_stint(None)` marks the change unconfirmed, remembers the stop lap and
holds the pre-stop reading as the baseline; the gauge settles it - two
readings for a fresh set, never one, because an all-zero misread is on file;
and the driver's word settles it outright. While it is open the wear call
says nothing.
"""
from __future__ import annotations

import pytest

from pitcrew.race.calls import (GAUGE_FRESH_SET_MAX, RaceState, _wear,
                                clear_stint)
from pitcrew.telemetry.session_state import EventKind, SessionKind, SessionState

from .conftest import make_packet
from .test_session_state import feed, filling, kinds


# --------------------------------------------------------------- the event

def test_a_stop_with_no_swap_seen_says_unknown_not_no():
    state = SessionState(SessionKind.PRACTICE)
    packets = [make_packet(speed_ms=30.0, fuel_level=10.0),
               make_packet(speed_ms=5.0, fuel_level=10.0)]
    packets += filling(10.0, seconds=20.0)
    packets.append(make_packet(speed_ms=40.0, fuel_level=30.0))
    events = feed(state, packets)

    assert kinds(events) == [EventKind.PIT_ENTRY, EventKind.PIT_EXIT]
    assert events[0].data["tyres_changed"] is None
    assert events[1].data["tyres_changed"] is None
    feed(state, [make_packet(speed_ms=40.0, fuel_level=29.0,
                             last_lap_ms=120_000)])
    assert state.laps[0].tyres_changed is None


def test_a_swap_that_is_seen_is_true():
    state = SessionState(SessionKind.PRACTICE)
    hot = dict(tyre_temp_fl=80.0, tyre_temp_fr=80.0, tyre_temp_rl=80.0, tyre_temp_rr=80.0)
    cold = dict(tyre_temp_fl=60.0, tyre_temp_fr=60.0, tyre_temp_rl=60.0, tyre_temp_rr=60.0)
    packets = [make_packet(speed_ms=30.0, fuel_level=10.0, **hot),
               make_packet(speed_ms=1.0, fuel_level=10.0, **hot),
               make_packet(speed_ms=1.0, fuel_level=10.0, **cold)]
    packets += filling(10.0, seconds=20.0)
    packets.append(make_packet(speed_ms=40.0, fuel_level=30.0, **cold))
    events = feed(state, packets)
    exits = [e for e in events if e.kind is EventKind.PIT_EXIT]
    assert exits and exits[0].data["tyres_changed"] is True


# ------------------------------------------------------------ clear_stint

def _after_unknown_stop(before=0.42):
    state = RaceState(lap=13, laps_since_stop=13, laps_total=20,
                      wear_history=[(12, {"fl": before - 0.07, "fr": before})])
    clear_stint(state, tyres_changed=None)
    return state


def test_an_unknown_stop_is_marked_unconfirmed_and_holds_its_baseline():
    state = _after_unknown_stop()
    assert state.tyre_change_unconfirmed is True
    assert state.unconfirmed_stop_lap == 13
    assert state.unconfirmed_before == 0.42
    assert state.laps_since_stop == 13, "the count carries on until resolved"
    assert state.wear_history, "history is kept until the gauge says otherwise"


def test_a_seen_swap_resets_everything_and_says_who_saw_it():
    state = RaceState(lap=13, laps_since_stop=13,
                      wear_history=[(12, {"fr": 0.42})])
    clear_stint(state, tyres_changed=True)
    assert state.tyre_change_unconfirmed is False
    assert state.laps_since_stop == 0
    assert state.wear_history == []
    assert state.tyre_change_resolution == "session: swap seen"


# ---------------------------------------------------------- the resolution

def test_one_near_zero_reading_is_parked_not_believed():
    """An all-four-corners 0.000 misread is a documented gauge failure."""
    state = _after_unknown_stop()
    state.note_wear(14, {"fl": 0.0, "fr": 0.0})
    assert state.tyre_change_unconfirmed is True
    assert state.tyre_change_resolution is None
    assert state.parked_wear == [(14, {"fl": 0.0, "fr": 0.0})]
    assert state.wear_history == [(12, {"fl": 0.35, "fr": 0.42})], "untouched"


def test_two_readings_near_zero_are_a_fresh_set():
    """Deep Forest: 0.42 before the stop, then 0.00 and 0.03 after it."""
    state = _after_unknown_stop()
    state.note_wear(14, {"fl": 0.0, "fr": 0.0})
    state.note_wear(15, {"fl": 0.02, "fr": 0.028})

    assert state.tyre_change_unconfirmed is False
    assert state.tyre_change_resolution == "gauge: fresh set"
    assert state.laps_since_stop == 2, "two laps on the new set: 15 - 13"
    assert state.wear_history == [(14, {"fl": 0.0, "fr": 0.0}),
                                  (15, {"fl": 0.02, "fr": 0.028})]
    assert state.parked_wear == []
    assert state.tyre_change_write_back == (13, True, "gauge: fresh set")


def test_the_gauge_carrying_on_resolves_it_as_the_same_set():
    state = _after_unknown_stop()
    state.note_wear(14, {"fl": 0.37, "fr": 0.45})

    assert state.tyre_change_unconfirmed is False
    assert state.tyre_change_resolution == "gauge: same set"
    assert state.laps_since_stop == 13, "the count was right all along"
    assert len(state.wear_history) == 2
    assert state.tyre_change_write_back == (13, False, "gauge: same set")


def test_a_partial_drop_does_not_move_the_baseline():
    """0.42 -> 0.11 -> 0.13 used to read 'same set' against 0.11 (rule 10).
    Every reading is judged against the pre-stop 0.42 until it is settled."""
    state = _after_unknown_stop()
    state.note_wear(14, {"fr": 0.11})
    assert state.tyre_change_unconfirmed is True
    state.note_wear(15, {"fr": 0.13})
    # 0.13 is under the ceiling and 0.29 below the baseline, and the reading
    # before it agrees: a fresh set, not "same set" against 0.11.
    assert state.tyre_change_resolution == "gauge: fresh set"
    assert state.unconfirmed_before is None


def test_a_reading_that_is_neither_shape_waits():
    state = _after_unknown_stop()
    state.note_wear(14, {"fr": 0.25})
    assert state.tyre_change_unconfirmed is True
    assert state.parked_wear and state.wear_history[-1][0] == 12


def test_a_fresh_set_needs_the_second_reading_no_lower_than_the_first():
    """0.00 then 0.09 is a set wearing; 0.09 then 0.00 is the locator."""
    state = _after_unknown_stop()
    state.note_wear(14, {"fr": 0.09})
    state.note_wear(15, {"fr": 0.0})
    assert state.tyre_change_unconfirmed is True


def test_no_reading_before_the_stop_cannot_be_settled_by_the_gauge():
    state = RaceState(lap=13, laps_since_stop=13)
    clear_stint(state, tyres_changed=None)
    assert state.unconfirmed_before is None
    state.note_wear(14, {"fr": 0.0})
    state.note_wear(15, {"fr": 0.01})
    assert state.tyre_change_unconfirmed is True


def test_a_confirmed_stop_is_not_second_guessed_by_the_gauge():
    state = RaceState(lap=13, laps_since_stop=13,
                      wear_history=[(12, {"fr": 0.42})])
    clear_stint(state, tyres_changed=True)
    state.note_wear(14, {"fr": 0.03})
    assert state.tyre_change_resolution == "session: swap seen"
    assert state.laps_since_stop == 0


def test_the_fresh_set_ceiling_is_the_gauges_own():
    from pitcrew.telemetry.hud import FRESH_SET_MAX
    assert GAUGE_FRESH_SET_MAX == FRESH_SET_MAX


# ---------------------------------------------------------- the driver's word

def test_the_drivers_word_settles_it_outright():
    state = _after_unknown_stop()
    state.note_tyres_word(True, lap=14)
    assert state.tyre_change_unconfirmed is False
    assert state.tyre_change_resolution == "driver: new tyres"
    assert state.laps_since_stop == 1
    assert state.wear_history == []
    assert state.tyre_change_write_back == (13, True, "driver: new tyres")


def test_no_tyres_from_the_driver_keeps_the_history():
    state = _after_unknown_stop()
    state.note_wear(14, {"fr": 0.0})           # parked
    state.note_tyres_word(False, lap=14)
    assert state.tyre_change_resolution == "driver: no tyres"
    assert state.laps_since_stop == 13
    assert state.wear_history[-1] == (14, {"fr": 0.0})


def test_the_driver_overrules_a_gauge_that_settled_it_the_other_way():
    state = _after_unknown_stop()
    state.note_wear(14, {"fl": 0.37, "fr": 0.45})
    assert state.tyre_change_resolution == "gauge: same set"
    state.note_tyres_word(True, lap=15)
    assert state.tyre_change_resolution == "driver: new tyres"
    assert state.laps_since_stop == 0


# ------------------------------------------------------- the wear call waits

def test_the_wear_projection_is_silent_through_an_unconfirmed_stop():
    """'Box this lap. FR at 42 percent, measured.' on the out-lap of a fresh
    set was the Deep Forest failure with the word 'measured' attached. The
    projection every wear call rests on is None while the stop is open, and
    comes back on the NEW set's count once the gauge has settled it."""
    from pitcrew.race.calls import _wear_laps_left

    state = RaceState(lap=13, laps_total=20, laps_since_stop=13,
                      briefed_wear_per_lap=0.035, briefed_wear_samples=9,
                      wear_history=[(12, {"fr": 0.42}), (13, {"fr": 0.45})])
    before = _wear_laps_left(state)
    assert before is not None and before.consumed == pytest.approx(0.45)
    clear_stint(state, tyres_changed=None)
    state.lap = 14
    assert _wear_laps_left(state) is None, "the old set may not be projected"
    assert _wear(state) is None
    state.note_wear(14, {"fr": 0.0})
    state.lap = 15
    assert _wear_laps_left(state) is None, "one reading is not a settlement"
    state.note_wear(15, {"fr": 0.02})
    state.lap = 16
    after = _wear_laps_left(state)
    assert after is not None
    assert after.consumed < 0.1, "the new set, not 45 percent plus three laps"
