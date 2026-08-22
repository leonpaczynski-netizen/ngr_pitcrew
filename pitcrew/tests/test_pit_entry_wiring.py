"""The frame-exact pit entry, and the racing it lets us measure either side.

`pit_detect.pit_entry_frame` and `entered_the_pits` were written on 18 Aug from
a measurement - **GT7 takes the car over at pit entry and the speed drops from
racing to nothing between two consecutive frames**, measured at Monza as
145.6 / 227.3 / 226.3 / 211.1 kph to zero, once per pit lap and never outbound -
and then nothing ever called them. The live detector went on inferring pit
entry from the tank starting to climb, which is several seconds later.

That lateness is why this matters. Every Monza race on file recorded 26 rows
for 27 laps driven: the crossing inside the pit sequence never reaches the app,
so one row holds nearly two laps, the count comes out one light, and
`fuel_target_l` asks for a lap of fuel too much - about six litres, six seconds
standing still at the measured 1 L/s.
"""
from __future__ import annotations

from pitcrew.telemetry.pit_detect import PIT_ENTRY_FROM_KPH
from pitcrew.telemetry.session_state import (
    EventKind,
    SessionKind,
    SessionState,
)

from .conftest import make_packet


def run(state: SessionState, packets) -> list:
    events = []
    for packet in packets:
        events.extend(state.update(packet))
    return events


def stream(*specs, start_id: int = 1):
    """Packets with CONSECUTIVE ids, which is what the detector requires.

    `make_packet` leaves `packet_id` at 0, so a fixture that does not set it
    describes a stream where every frame arrived at the same instant - and the
    adjacency guard correctly refuses to read a speed step out of that.
    """
    out = []
    for offset, spec in enumerate(specs):
        out.append(make_packet(packet_id=start_id + offset, **spec))
    return out


def kinds(events):
    return [event.kind for event in events]


def entry_of(events):
    return next((e for e in events if e.kind is EventKind.PIT_ENTRY), None)


# --------------------------------------------------------------- it fires

def test_the_speed_step_is_a_pit_entry():
    """Racing to nothing between two adjacent frames. No car does this."""
    state = SessionState(SessionKind.RACE)
    events = run(state, stream(
        {"speed_ms": 60.0},          # 216 kph
        {"speed_ms": 60.0},
        {"speed_ms": 0.0},           # taken by the game
    ))
    found = entry_of(events)
    assert found is not None
    assert found.data["by"] == "speed-step"


def test_it_beats_the_fuel_signal_to_it():
    """The whole point: the tank only starts climbing seconds later, and a
    figure measured from that signal charges the stop's opening to driving."""
    state = SessionState(SessionKind.RACE)
    events = run(state, stream(
        {"speed_ms": 60.0, "fuel_level": 40.0},
        {"speed_ms": 0.0, "fuel_level": 40.0},      # entry, no fuel yet
        {"speed_ms": 0.0, "fuel_level": 45.0},      # refuelling starts here
    ))
    assert entry_of(events).data["by"] == "speed-step"
    assert kinds(events).count(EventKind.PIT_ENTRY) == 1


# ------------------------------------------------------------ it refuses

def test_a_dropped_datagram_is_not_a_pit_entry():
    """**The false positive the adjacency guard exists for.** A lost packet
    can put 216 kph next to 0 kph in the received stream with an ordinary
    braking zone in between, and that is not a stop."""
    state = SessionState(SessionKind.RACE)
    packets = stream({"speed_ms": 60.0}, {"speed_ms": 60.0})
    late = make_packet(packet_id=99, speed_ms=0.0)     # a gap in the counter
    assert entry_of(run(state, packets + [late])) is None


def test_a_normal_deceleration_is_not_a_pit_entry():
    """Braking takes many frames. Only the game stops a car in one."""
    state = SessionState(SessionKind.RACE)
    speeds = [60.0, 50.0, 40.0, 30.0, 20.0, 10.0, 4.0, 0.0]
    events = run(state, stream(*({"speed_ms": v} for v in speeds)))
    assert entry_of(events) is None


def test_a_step_that_does_not_start_above_the_threshold_is_not_one():
    state = SessionState(SessionKind.RACE)
    slow = (PIT_ENTRY_FROM_KPH - 20.0) / 3.6
    events = run(state, stream({"speed_ms": slow}, {"speed_ms": 0.0}))
    assert entry_of(events) is None


def test_off_track_is_still_no_pit_entry():
    """Returning to the garage is not a stop, and never was."""
    state = SessionState(SessionKind.RACE)
    events = run(state, [make_packet(packet_id=1, speed_ms=60.0),
                         make_packet(packet_id=2, speed_ms=0.0,
                                     on_track=False)])
    assert entry_of(events) is None


# ------------------------------------------------- the racing either side

def test_a_pit_lap_reports_the_racing_it_actually_did(monkeypatch):
    """`(entry - lap start) + (crossing - exit)`, with the stop excluded by
    construction - which is what makes it independent of how long the stop was.

    The clock is driven so the arithmetic is actually asserted: 40 s of racing
    in, a 70 s stop, 50 s of racing out. The answer must be 90 s and must not
    contain a second of the stop - a figure that swallowed it would read as
    two laps of driving and manufacture the very dropped crossing this is
    supposed to detect.
    """
    ticks = iter([0.0, 40.0, 60.0, 110.0, 160.0])
    monkeypatch.setattr("pitcrew.telemetry.session_state.time.monotonic",
                        lambda: next(ticks))
    state = SessionState(SessionKind.RACE)
    run(state, stream(
        {"speed_ms": 60.0, "fuel_level": 40.0},       # t=0,   lap start
        {"speed_ms": 0.0, "fuel_level": 40.0},        # t=40,  entry
        {"speed_ms": 0.0, "fuel_level": 70.0},        # t=60,  filling
        {"speed_ms": 60.0, "fuel_level": 70.0},       # t=110, release
        {"speed_ms": 60.0, "fuel_level": 68.0,        # t=160, crossing
         "last_lap_ms": 183_000},
    ))
    assert state.laps and state.laps[-1].is_pit_lap
    # 40 in + 50 out = 90 s, and none of the 70 s stop.
    assert state.laps[-1].pit_racing_ms == 90_000


def test_an_ordinary_lap_claims_no_racing_figure():
    state = SessionState(SessionKind.RACE)
    run(state, stream({"speed_ms": 60.0},
                      {"speed_ms": 60.0, "last_lap_ms": 92_000}))
    assert state.laps[-1].pit_racing_ms is None


def test_a_stop_still_in_progress_reports_nothing():
    """**A partial figure is worse than none**: without the release it is
    indistinguishable from a short lap, which is the opposite of the finding
    it exists to support."""
    state = SessionState(SessionKind.RACE)
    run(state, stream(
        {"speed_ms": 60.0, "fuel_level": 40.0},
        {"speed_ms": 0.0, "fuel_level": 40.0},
        {"speed_ms": 0.0, "fuel_level": 70.0, "last_lap_ms": 183_000},
    ))
    assert state.laps[-1].pit_racing_ms is None


def test_the_figure_does_not_survive_into_the_next_lap():
    state = SessionState(SessionKind.RACE)
    run(state, stream(
        {"speed_ms": 60.0, "fuel_level": 40.0},
        {"speed_ms": 0.0, "fuel_level": 40.0},
        {"speed_ms": 0.0, "fuel_level": 70.0},
        {"speed_ms": 60.0, "fuel_level": 70.0},
        {"speed_ms": 60.0, "fuel_level": 68.0, "last_lap_ms": 183_000},
        {"speed_ms": 60.0, "fuel_level": 62.0, "last_lap_ms": 92_000},
    ))
    assert state.laps[-1].pit_racing_ms is None
    assert not state.laps[-1].is_pit_lap
