"""Lap, race-start and pit detection."""
from __future__ import annotations

import pytest

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


def test_a_crossing_off_track_is_still_a_crossing():
    """GT7 clears `car_on_track` through its pit sequence.

    This used to assert the opposite, and the opposite is what filed 19 rows
    for the 20-lap Fuji race: at a circuit whose pit lane spans the line the
    stop straddles a lap, so the one crossing the gate reliably threw away was
    the one taken at pit-lane speed. Being off track is a reason to doubt the
    lap's fuel and tyre readings, not a reason to pretend the lap did not
    happen.
    """
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [make_packet(), make_packet(last_lap_ms=92_000, on_track=False)])
    assert state.lap_count == 1


def test_a_lap_time_already_on_the_stream_does_not_file_a_lap():
    """What the off-track gate was really protecting against.

    The latch fires on a change, so it has to be seeded from the first packet:
    joining a session in progress - or opening on a menu still holding the
    last session's time - otherwise files a lap nobody drove.
    """
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [make_packet(last_lap_ms=92_000),
                 make_packet(last_lap_ms=92_000)])
    assert state.lap_count == 0


def test_one_discarded_frame_does_not_cost_a_lap():
    """The defect itself: an edge latched against the previous FRAME.

    A paused frame carrying the new lap time used to advance the comparison
    without filing anything, and the `!=` was false from then on - the lap
    gone, silently, for one skipped frame.
    """
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [make_packet(),
                 make_packet(last_lap_ms=92_000, flags_raw=0x0001 | 0x0002),
                 make_packet(last_lap_ms=92_000)])
    assert state.lap_count == 1


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
#
# The fills below are written at GT7's real rate rather than as a single jump.
# A jump is not a shortcut for a fill: an instantaneous tank is the signature
# of the garage handing the car back, and `_refuelling` now refuses it.

def filling(from_l: float, seconds: float, speed_ms: float = 0.0):
    """Packets covering a fill at GT7's measured ~1 L/s, 60 Hz."""
    return [make_packet(speed_ms=speed_ms,
                        fuel_level=from_l + n * REAL_FILL_L_PER_FRAME)
            for n in range(int(seconds * 60))]


def test_pit_entry_and_exit_from_refuelling():
    state = SessionState(SessionKind.PRACTICE)
    packets = [make_packet(speed_ms=30.0, fuel_level=10.0),
               make_packet(speed_ms=5.0, fuel_level=10.0)]   # crawling in
    packets += filling(10.0, seconds=20.0)
    packets.append(make_packet(speed_ms=40.0, fuel_level=30.0))   # away
    events = feed(state, packets)
    assert kinds(events) == [EventKind.PIT_ENTRY, EventKind.PIT_EXIT]
    assert events[1].data["fuel_added"] == pytest.approx(20.0, abs=0.5)


def test_lap_after_a_pit_stop_is_flagged():
    state = SessionState(SessionKind.PRACTICE)
    packets = [make_packet(speed_ms=5.0, fuel_level=10.0)]
    packets += filling(10.0, seconds=10.0)
    packets.append(make_packet(speed_ms=40.0, fuel_level=20.0))
    packets.append(make_packet(speed_ms=40.0, fuel_level=18.0,
                               last_lap_ms=120_000))
    feed(state, packets)
    assert state.laps[0].is_pit_lap is True
    assert state.laps[0].is_out_lap is True


def test_a_tank_handed_back_full_in_one_frame_is_not_a_refuel():
    """Session 16 lap 1: 96.192 -> 100.000 between two packets at 0.00 km/h.

    That is 228 L/s against a rig that delivers about one, and it is what a
    garage return looks like from here.  Taken as a stop it marked a 113 s lap
    the driver actually drove as a pit lap with 3.47 L added, dropped it and
    the lap after it from the counted set, and reported a stop that never
    happened.
    """
    state = SessionState(SessionKind.PRACTICE)
    packets = [make_packet(speed_ms=0.0, fuel_level=96.192) for _ in range(120)]
    packets.append(make_packet(speed_ms=0.0, fuel_level=100.0))
    assert EventKind.PIT_ENTRY not in kinds(feed(state, packets))


def test_a_stop_is_never_inferred_with_the_car_off_track():
    """Returning to the garage refills the tank and refits the tyres -- both
    signatures at once, and neither of them a pit stop."""
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [make_packet(speed_ms=30.0, fuel_level=40.0)])
    garage = [make_packet(speed_ms=0.0, fuel_level=40.0, on_track=False)]
    garage += [make_packet(speed_ms=0.0, fuel_level=40.0 + n * 1.0,
                           on_track=False,
                           tyre_temp_fl=60.0, tyre_temp_fr=60.0,
                           tyre_temp_rl=60.0, tyre_temp_rr=60.0)
               for n in range(1, 61)]
    assert EventKind.PIT_ENTRY not in kinds(feed(state, garage))


def test_the_fuel_window_does_not_survive_a_pause():
    """A reading from before a load screen against the first one after it is
    not a measurement of anything -- and it fired PIT_ENTRY with 40 litres on
    the first packet of a restarted race, with the car on track throughout."""
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [make_packet(speed_ms=0.0, fuel_level=40.0) for _ in range(60)])
    events = feed(state, [
        make_packet(speed_ms=0.0, fuel_level=40.0, flags_raw=0x0003),  # paused
        make_packet(speed_ms=0.0, fuel_level=100.0),
    ])
    assert EventKind.PIT_ENTRY not in kinds(events)


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


# ------------------------------------------- the stop the app could never see
#
# These are built from session 19 lap 14 of the capture set — the only pit stop
# in the database, and the one every detector in the app missed.  The numbers
# are the measured ones, not illustrative: 51 L over 63 s at 60 Hz, and the
# tyre swap three seconds before the fuel started.

REAL_FILL_L_PER_FRAME = 0.0167          # 1 L/s at 60 Hz, measured
REAL_HOT = (73.8, 67.6, 82.9, 79.8)     # the set as it came in
REAL_FITTED = (60.0, 60.0, 60.0, 60.0)  # the set as GT7 fitted it


def stationary(fuel: float, temps=REAL_HOT):
    return make_packet(speed_ms=0.0, fuel_level=fuel,
                       tyre_temp_fl=temps[0], tyre_temp_fr=temps[1],
                       tyre_temp_rl=temps[2], tyre_temp_rr=temps[3])


def test_a_real_refuel_is_seen_although_no_two_frames_differ_by_much():
    """The regression that mattered.

    GT7 fills at ~1 L/s, so at 60 Hz no two consecutive frames differ by more
    than 0.017 L.  The gate this replaced wanted 0.05 L between frames and so
    never fired once across 132 recorded laps.
    """
    state = SessionState(SessionKind.PRACTICE)
    fuel = 14.65
    packets = [make_packet(speed_ms=30.0, fuel_level=fuel),
               stationary(fuel)]
    for _ in range(300):                       # five seconds of filling
        fuel += REAL_FILL_L_PER_FRAME
        packets.append(stationary(fuel))

    events = feed(state, packets)
    assert EventKind.PIT_ENTRY in kinds(events)
    assert state.phase is Phase.IN_PIT
    # No single frame in that fill clears the old threshold.
    assert REAL_FILL_L_PER_FRAME < 0.05


def test_a_tyres_only_stop_is_seen_with_no_fuel_at_all():
    """Previously unreachable: pit entry could only be entered through fuel."""
    state = SessionState(SessionKind.PRACTICE)
    events = feed(state, [
        make_packet(speed_ms=30.0, fuel_level=40.0),
        stationary(40.0),
        stationary(40.0, REAL_FITTED),        # all four step together
    ])
    assert EventKind.PIT_ENTRY in kinds(events)
    entry = next(e for e in events if e.kind is EventKind.PIT_ENTRY)
    assert entry.data["tyres_changed"] is True


def test_the_lap_carrying_the_stop_records_what_was_done_to_the_car():
    state = SessionState(SessionKind.PRACTICE)
    fuel = 20.0
    packets = [make_packet(speed_ms=30.0, fuel_level=fuel), stationary(fuel)]
    packets.append(stationary(fuel, REAL_FITTED))
    for _ in range(120):
        fuel += REAL_FILL_L_PER_FRAME
        packets.append(stationary(fuel, REAL_FITTED))
    packets.append(make_packet(speed_ms=60.0, fuel_level=fuel,
                               last_lap_ms=182_408))
    feed(state, packets)

    lap = state.laps[0]
    assert lap.is_pit_lap is True
    assert lap.tyres_changed is True
    assert lap.fuel_added_l == pytest.approx(2.0, abs=0.1)


def test_a_lap_with_no_stop_makes_no_claim_about_the_tyres():
    """`None`, not `False`.  Nothing was asked, so nothing is answered."""
    state = SessionState(SessionKind.PRACTICE)
    feed(state, [make_packet(fuel_level=60.0),
                 make_packet(fuel_level=58.0, last_lap_ms=92_000)])
    assert state.laps[0].tyres_changed is None
    assert state.laps[0].fuel_added_l is None


def test_cooling_tyres_are_not_a_tyre_change():
    """A stationary car cools a little.  That is not a set coming off, and the
    corners stay uneven while it happens."""
    state = SessionState(SessionKind.PRACTICE)
    cooling = [(t - 4.0) for t in REAL_HOT]
    events = feed(state, [make_packet(speed_ms=30.0, fuel_level=40.0),
                          stationary(40.0),
                          stationary(40.0, cooling)])
    assert EventKind.PIT_ENTRY not in kinds(events)


def test_four_even_temperatures_at_racing_speed_are_not_a_stop():
    state = SessionState(SessionKind.PRACTICE)
    events = feed(state, [
        make_packet(speed_ms=60.0, fuel_level=40.0,
                    tyre_temp_fl=REAL_HOT[0], tyre_temp_fr=REAL_HOT[1],
                    tyre_temp_rl=REAL_HOT[2], tyre_temp_rr=REAL_HOT[3]),
        make_packet(speed_ms=60.0, fuel_level=40.0,
                    tyre_temp_fl=60.0, tyre_temp_fr=60.0,
                    tyre_temp_rl=60.0, tyre_temp_rr=60.0),
    ])
    assert EventKind.PIT_ENTRY not in kinds(events)


def test_a_slow_fuel_drain_never_reads_as_a_fill():
    state = SessionState(SessionKind.PRACTICE)
    packets = [make_packet(speed_ms=20.0, fuel_level=50.0 - n * 0.02)
               for n in range(200)]
    assert EventKind.PIT_ENTRY not in kinds(feed(state, packets))


def test_a_stop_that_straddles_the_line_keeps_its_fill():
    """Session 127 lap 13, Daytona, 4 Sep 2026.

    GT7 puts the start/finish line inside the pit lane at Daytona, Fuji and
    Monza, so the crossing fires while the car is standing in the box: the
    ENTRY lands on one lap and the FILL on the next.  The close used to clear
    `_fuel_added_in_stop` at every crossing, so the fill - measured correctly,
    seconds later - was discarded, the out-lap's arithmetic went negative, and
    `_burn` clamped it to a fabricated `fuel_used = 0.0` with `fuel_added_l`
    NULL beside it.  Measured that night: 6.81 -> 62.96 L in the box and about
    7 L burned finishing the lap, filed as zero.

    CLAUDE.md rule 9: a quantity that came out negative is a reading whose
    reference is wrong, not a quantity of zero.
    """
    state = SessionState(SessionKind.RACE)
    packets = [make_packet(speed_ms=30.0, fuel_level=10.0),
               make_packet(speed_ms=5.0, fuel_level=10.0)]      # crawling in
    packets += filling(10.0, seconds=5.0)
    # The line goes by while he is still standing in the box.
    packets.append(make_packet(speed_ms=0.0, fuel_level=15.0,
                               last_lap_ms=120_000))
    packets += filling(15.0, seconds=25.0)                      # fill continues
    packets.append(make_packet(speed_ms=40.0, fuel_level=40.0))  # away
    packets.append(make_packet(speed_ms=40.0, fuel_level=33.0,
                               last_lap_ms=110_000))            # out lap ends
    feed(state, packets)

    assert len(state.laps) == 2
    out_lap = state.laps[1]
    # It ended fuller than it started, and that is a fill, not an un-burn.
    assert out_lap.fuel_start < out_lap.fuel_end
    assert out_lap.fuel_added_l is not None and out_lap.fuel_added_l > 0
    # start - end + added, and emphatically not 0.0.
    assert out_lap.fuel_used > 0.0
    assert out_lap.fuel_used == pytest.approx(
        out_lap.fuel_start - out_lap.fuel_end + out_lap.fuel_added_l, abs=0.2)
