"""Lap, race-start and pit detection."""
from __future__ import annotations

from pitcrew.telemetry.session_state import (
    EventKind,
    Phase,
    SessionKind,
    SessionState,
)

from .conftest import make_packet


def feed(state: SessionState, packets) -> list:
    events = []
    for pkt in packets:
        events.extend(state.update(pkt))
    return events


def kinds(events) -> list[EventKind]:
    return [event.kind for event in events]


# ----------------------------------------------------------------- lap timing

def test_lap_fires_on_new_last_lap_ms():
    state = SessionState(SessionKind.PRACTICE)
    events = feed(state, [
        make_packet(fuel_level=60.0),
        make_packet(fuel_level=58.0, last_lap_ms=92_000, best_lap_ms=92_000),
    ])
    assert kinds(events) == [EventKind.LAP_COMPLETED]
    lap = events[0].data["lap"]
    assert lap.lap_num == 1
    assert lap.lap_time_ms == 92_000
    assert lap.fuel_used == 2.0


def test_repeated_last_lap_ms_does_not_refire():
    state = SessionState(SessionKind.PRACTICE)
    events = feed(state, [
        make_packet(),
        make_packet(last_lap_ms=92_000),
        make_packet(last_lap_ms=92_000),
        make_packet(last_lap_ms=92_000),
    ])
    assert len(events) == 1


def test_lap_numbering_ignores_gt7_lap_counter():
    """GT7's laps_completed is unreliable; numbering comes from our own history."""
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [
        make_packet(),
        make_packet(last_lap_ms=92_000, laps_completed=7),
        make_packet(last_lap_ms=91_000, laps_completed=7),
        make_packet(last_lap_ms=90_500, laps_completed=99),
    ])
    assert [lap.lap_num for lap in state.laps] == [1, 2, 3]


def test_delta_is_versus_best():
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [
        make_packet(),
        make_packet(last_lap_ms=93_000, best_lap_ms=91_000),
    ])
    assert state.laps[0].delta_ms == 2_000


def test_no_lap_while_off_track():
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [make_packet(), make_packet(last_lap_ms=92_000, on_track=False)])
    assert state.lap_count == 0


def test_paused_packets_are_ignored():
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [make_packet(), make_packet(last_lap_ms=92_000, flags_raw=0x0001 | 0x0002)])
    assert state.lap_count == 0


# ---------------------------------------------------------------- race start

def test_race_starts_after_grid_then_speed():
    state = SessionState(SessionKind.RACE)
    events = feed(state, [
        make_packet(speed_ms=0.0, laps_in_race=12),      # on the grid
        make_packet(speed_ms=10.0, laps_in_race=12),     # 36 km/h
        make_packet(speed_ms=30.0, laps_in_race=12),     # 108 km/h -> lights out
    ])
    assert EventKind.RACE_STARTED in kinds(events)
    assert state.phase is Phase.RACING
    assert state.laps_in_race == 12


def test_race_does_not_start_mid_session_at_speed():
    """App started during a flying lap: no grid seen, no lap counter change."""
    state = SessionState(SessionKind.RACE)
    events = feed(state, [
        make_packet(speed_ms=60.0, laps_in_race=12),
        make_packet(speed_ms=62.0, laps_in_race=12),
        make_packet(speed_ms=64.0, laps_in_race=12),
    ])
    assert EventKind.RACE_STARTED not in kinds(events)
    assert state.phase is Phase.ON_TRACK


def test_rolling_start_fires_on_line_crossing():
    """Never drops below 30 km/h, so only the lap-counter branch can fire."""
    state = SessionState(SessionKind.RACE)
    events = feed(state, [
        make_packet(speed_ms=40.0, laps_completed=0, laps_in_race=8),
        make_packet(speed_ms=42.0, laps_completed=1, laps_in_race=8),
    ])
    assert EventKind.RACE_STARTED in kinds(events)


def test_race_length_uses_pre_start_maximum():
    """Grid behind the line: GT7 has already decremented by the time we start."""
    state = SessionState(SessionKind.RACE)
    feed(state, [
        make_packet(speed_ms=0.0, laps_in_race=10),
        make_packet(speed_ms=5.0, laps_in_race=10),
        make_packet(speed_ms=30.0, laps_in_race=9),   # decremented at the crossing
    ])
    assert state.laps_in_race == 10


def test_practice_never_starts_a_race():
    state = SessionState(SessionKind.PRACTICE)
    events = feed(state, [
        make_packet(speed_ms=0.0, laps_in_race=12),
        make_packet(speed_ms=40.0, laps_in_race=12),
    ])
    assert EventKind.RACE_STARTED not in kinds(events)
    assert state.phase is Phase.ON_TRACK


def test_race_finishes_on_final_lap():
    state = SessionState(SessionKind.RACE)
    feed(state, [
        make_packet(speed_ms=0.0, laps_in_race=2),
        make_packet(speed_ms=30.0, laps_in_race=2),
    ])
    events = feed(state, [
        make_packet(speed_ms=30.0, last_lap_ms=92_000),
        make_packet(speed_ms=30.0, last_lap_ms=91_000),
    ])
    assert kinds(events)[-1] is EventKind.RACE_FINISHED
    assert state.phase is Phase.FINISHED


# ----------------------------------------------------------------------- pit

def test_pit_entry_and_exit_from_refuelling():
    state = SessionState(SessionKind.PRACTICE)
    events = feed(state, [
        make_packet(speed_ms=30.0, fuel_level=10.0),
        make_packet(speed_ms=5.0, fuel_level=10.0),      # crawling in the box
        make_packet(speed_ms=0.0, fuel_level=25.0),      # refuelling
        make_packet(speed_ms=0.0, fuel_level=45.0),
        make_packet(speed_ms=40.0, fuel_level=45.0),     # away
    ])
    assert kinds(events) == [EventKind.PIT_ENTRY, EventKind.PIT_EXIT]
    assert events[1].data["fuel_added"] == 35.0


def test_lap_after_a_pit_stop_is_flagged():
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [
        make_packet(speed_ms=5.0, fuel_level=10.0),
        make_packet(speed_ms=0.0, fuel_level=40.0),      # pit entry
        make_packet(speed_ms=40.0, fuel_level=40.0),     # pit exit
        make_packet(speed_ms=40.0, fuel_level=38.0, last_lap_ms=120_000),
    ])
    assert state.laps[0].is_pit_lap is True
    assert state.laps[0].is_out_lap is True


def test_fuel_rising_at_speed_is_not_a_pit_stop():
    state = SessionState(SessionKind.PRACTICE)
    events = feed(state, [
        make_packet(speed_ms=60.0, fuel_level=10.0),
        make_packet(speed_ms=60.0, fuel_level=12.0),
    ])
    assert kinds(events) == []


# ------------------------------------------------------------------ compound

def test_compound_can_be_tagged_after_the_lap():
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [make_packet(), make_packet(last_lap_ms=92_000)])
    assert state.laps[0].compound is None
    state.set_compound(1, "RM")
    assert state.laps[0].compound == "RM"


def test_laps_remaining_is_none_without_a_lap_count():
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [make_packet()])
    assert state.laps_remaining() is None
