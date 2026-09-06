"""A tyre change is seen, or unknown - never "no" because nothing looked.

Deep Forest, 6 Sep 2026, lap 13. The swap detector - all four corners stepping
down in one frame at walking pace - did not fire on a stop that fitted a fresh
set; PIT_EXIT then emitted `bool(None)` = False, the coordinator kept the old
set's wear history, the live fit ran through 0.42 -> 0.00 -> 0.03 and the
briefed projection counted thirteen laps on a one-lap-old set. The gauge had
read the fresh set the whole time and nothing asked it.

Three things, all here: the session emits True or None, never a default False;
`clear_stint(None)` marks the change unconfirmed and remembers the stop lap;
the first gauge reading after it settles the question either way.
"""
from __future__ import annotations

import pytest

from pitcrew.race.calls import (GAUGE_FRESH_SET_DROP, GAUGE_FRESH_SET_MAX,
                                RaceState, clear_stint)
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
    # And the lap row filed after the stop carries the same unknown.
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

def test_an_unknown_stop_is_marked_unconfirmed_and_its_lap_remembered():
    state = RaceState(lap=13, laps_since_stop=13,
                      wear_history=[(12, {"fl": 0.35, "fr": 0.42})])
    clear_stint(state, tyres_changed=None)
    assert state.tyre_change_unconfirmed is True
    assert state.unconfirmed_stop_lap == 13
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

def _after_unknown_stop(**history):
    state = RaceState(lap=13, laps_since_stop=13,
                      wear_history=[(12, {"fl": 0.35, "fr": 0.42})])
    clear_stint(state, tyres_changed=None)
    return state


def test_the_gauge_reading_a_fresh_set_resolves_it_as_changed():
    """Deep Forest: 0.42 before the stop, 0.00 on the first reading after."""
    state = _after_unknown_stop()
    state.note_wear(14, {"fl": 0.0, "fr": 0.028})

    assert state.tyre_change_unconfirmed is False
    assert state.tyre_change_resolution == "gauge: fresh set"
    assert state.laps_since_stop == 1, "one lap on the new set: 14 - 13"
    # The history restarts on the new set, and the new reading is its first.
    assert state.wear_history == [(14, {"fl": 0.0, "fr": 0.028})]
    assert state.unconfirmed_stop_lap is None


def test_the_gauge_carrying_on_resolves_it_as_the_same_set():
    state = _after_unknown_stop()
    state.note_wear(14, {"fl": 0.37, "fr": 0.45})

    assert state.tyre_change_unconfirmed is False
    assert state.tyre_change_resolution == "gauge: same set"
    assert state.laps_since_stop == 13, "the count was right all along"
    assert len(state.wear_history) == 2


def test_a_partial_drop_leaves_it_unconfirmed():
    """Neither shape - the next reading may settle it; a guess would not."""
    state = _after_unknown_stop()
    state.note_wear(14, {"fl": 0.20, "fr": 0.25})

    assert state.tyre_change_unconfirmed is True
    assert state.tyre_change_resolution is None


def test_the_fresh_set_test_needs_both_halves():
    """Near zero AND fallen: a set at 8% reading 8% again is the same set."""
    state = RaceState(lap=6, laps_since_stop=6,
                      wear_history=[(5, {"fr": 0.08})])
    clear_stint(state, tyres_changed=None)
    state.note_wear(7, {"fr": 0.08})

    assert state.tyre_change_resolution == "gauge: same set"
    assert GAUGE_FRESH_SET_MAX >= 0.08 > GAUGE_FRESH_SET_DROP - 0.1


def test_a_confirmed_stop_is_not_second_guessed_by_the_gauge():
    state = RaceState(lap=13, laps_since_stop=13,
                      wear_history=[(12, {"fr": 0.42})])
    clear_stint(state, tyres_changed=True)
    state.note_wear(14, {"fr": 0.03})
    assert state.tyre_change_resolution == "session: swap seen"
    assert state.laps_since_stop == 0


@pytest.mark.parametrize("before, after, expect", [
    (0.42, 0.00, "gauge: fresh set"),
    (0.42, 0.09, "gauge: fresh set"),
    (0.42, 0.11, None),                 # under the drop but over the max
    (0.42, 0.40, "gauge: same set"),
    (0.20, 0.04, "gauge: fresh set"),   # drop 0.16, max 0.04
    (0.12, 0.04, None),                 # drop 0.08 - not enough to be sure
])
def test_the_thresholds_read_the_two_halves_together(before, after, expect):
    state = RaceState(lap=13, laps_since_stop=13,
                      wear_history=[(12, {"fr": before})])
    clear_stint(state, tyres_changed=None)
    state.note_wear(14, {"fr": after})
    assert state.tyre_change_resolution == expect
