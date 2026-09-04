"""The three things the live engineer got wrong in session 127, pinned.

Daytona road course, 20 laps against the AI, 4 Sep 2026 22:12-22:50, Huracán
GT3 on RS. **P12 to P2, 23 s inside the plan** - and the driver reported three
faults unprompted, all three in one breath: *"engineer started late and had
laps wrong"*, and separately the fuel line that said a negative out loud.

Every number below is measured off that race - `data/pitcrew.db` session 127
and its lap-frame blobs, `race_revisions` for `race_run_id` 14, and
`logs/pitcrew.log` - and nothing here is synthetic except the packet shells
the fixtures are poured into.

* **The green fired at the lap-TWO crossing**, 22:16:25, 4 min 21 s after the
  session opened and 111.2 s of racing late, with `lap_num` 0 on the call and
  *"Lap 2."* one second behind it. Lap one got no calls at all. The same
  defect as Monza on 19 Aug 2026, latent two and a half weeks.
* **The spoken lap ran one behind his screen** for all 20 rows.
* **A fuel call went out as `-7.1 laps of fuel in hand to the flag`** with
  84.0 L aboard, 26 s after the same tank had been called *"1.9 spare to the
  stop."*
"""
from __future__ import annotations

from pitcrew.race.calls import (
    RaceState,
    _fuel_standing,
    fuel_in_hand,
    fuel_reference,
    orientation,
)
from pitcrew.race.clock import RaceClock
from pitcrew.race.colour import CHATTY, ColourCalls
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.telemetry.session_state import (
    EventKind,
    Lap,
    SessionEvent,
    SessionKind,
    SessionState,
)

from .conftest import make_packet

# Session 127's own figures, read back off the lap-one frame blob (7,034
# frames, 60 Hz) rather than chosen.
STALE_KMH = 278.7          # frames 0-1: the PREVIOUS session's last packet
STALE_LAPS_DONE = 5        # its lap counter, which is the poison
STALE_LAST_LAP_MS = 103_795
OPENING_KMH = 79.7         # frames 2-210: this race, from the line
LAP_ONE_MS = 111_166       # GT7's own figure for lap one


def kmh(value: float) -> float:
    return value / 3.6


def a_race() -> SessionState:
    return SessionState(SessionKind.RACE)


def feed(state: SessionState, packets) -> list[SessionEvent]:
    events: list[SessionEvent] = []
    for packet in packets:
        events.extend(state.update(packet))
    return events


# ------------------------------------------------------ 1. the green flag

def session_127_opening_frames() -> list:
    """The head of session 127's lap-one blob, frame for frame.

    Two frames of the previous session at 278.7 km/h carrying its lap counter
    at 5, then this race from the start/finish line at 79.7 km/h with the
    counter at 0, then GT7 ticking it to 1 at t = 5.87 s / 159 m to say lap
    one is under way. Nothing here ever drops below 30 km/h - Daytona's
    minimum over the rest of that lap is 58.9 km/h - and nothing reaches
    80 km/h either, so the launch branch cannot fire and the counter is the
    only signal there is.
    """
    stale = [make_packet(speed_ms=kmh(STALE_KMH),
                         laps_completed=STALE_LAPS_DONE,
                         last_lap_ms=STALE_LAST_LAP_MS,
                         laps_in_race=20)] * 2
    rolling = [make_packet(speed_ms=kmh(OPENING_KMH), laps_completed=0,
                           last_lap_ms=-1, laps_in_race=20)] * 4
    under_way = make_packet(speed_ms=kmh(OPENING_KMH), laps_completed=1,
                            last_lap_ms=-1, laps_in_race=20)
    return stale + rolling + [under_way]


def test_the_green_is_not_waiting_for_a_lap_to_complete():
    """**The whole of the defect, replayed off the frames that caused it.**

    Not one packet in this fixture completes a lap - `last_lap_ms` is never
    positive after the stale pair - so a green that arrives here arrived on
    the START. In the race it arrived 111.2 s later, on the lap-two crossing,
    because the baseline it compared against was the previous session's 5 and
    GT7's counter does not reach 6 until lap five.
    """
    state = a_race()
    events = feed(state, session_127_opening_frames())

    assert [e.kind for e in events] == [EventKind.RACE_STARTED]
    assert state.race_started
    assert events[0].data["laps_in_race"] == 20


def test_the_green_arrives_on_the_frame_gt7_says_lap_one_is_running():
    """Placed exactly, not merely present: it is the seventh packet, the one
    where GT7's counter goes 0 -> 1. In the race that frame was t = 5.87 s;
    the green actually spoken was at t = 111.2 s."""
    state = a_race()
    frames = session_127_opening_frames()
    before = feed(state, frames[:-1])
    assert before == [], "the green must not fire on the stale pair"
    assert not state.race_started

    assert [e.kind for e in feed(state, frames[-1:])] == [
        EventKind.RACE_STARTED]


def test_a_counter_that_never_drops_is_left_alone():
    """The retirement is a falsifier, not a reset. A session whose counter
    only rises - the ordinary case, and every rolling start - must behave
    exactly as it did."""
    state = a_race()
    events = feed(state, [
        make_packet(speed_ms=kmh(OPENING_KMH), laps_completed=3,
                    last_lap_ms=-1, laps_in_race=20),
        make_packet(speed_ms=kmh(OPENING_KMH), laps_completed=3,
                    last_lap_ms=-1, laps_in_race=20),
        make_packet(speed_ms=kmh(OPENING_KMH), laps_completed=4,
                    last_lap_ms=-1, laps_in_race=20),
    ])
    assert [e.kind for e in events] == [EventKind.RACE_STARTED]


def test_a_green_detected_after_racing_began_refuses_to_report_its_lag():
    """**CLAUDE.md rule 9, on the one line whose job is to report that lag.**

    Session 127 logged *"app clock: 0.00 s from green to the first crossing"*
    off a green 111.2 s late. The zero was not a measurement: `start()` had
    just back-dated the timer against the lap sum, which makes the difference
    approximately zero by construction. Clamped with `max(0.0, ...)`, it read
    as "the detector fired at lights out" - the one thing it cannot say.
    """
    ticks = {"s": 0.0}
    clock = RaceClock(None, now=lambda: ticks["s"])
    clock.start(LAP_ONE_MS, laps_before=1)      # the green, one lap late
    ticks["s"] = 105.7                          # lap two's crossing
    clock.note_lap(105_671, lap_num=2)

    assert clock.as_snapshot()["lapsBeforeClock"] == 1
    assert clock.as_snapshot()["greenToFirstCrossingS"] is None


def test_a_green_at_lights_out_still_measures_its_lag():
    """The refusal is not a blanket one - an ordinary race still gets the
    number, because there the gap between the green and the first crossing
    really is the grid period."""
    ticks = {"s": 0.0}
    clock = RaceClock(None, now=lambda: ticks["s"])
    clock.start()
    ticks["s"] = 114.0                          # 2.8 s of grid, then the lap
    clock.note_lap(111_166, lap_num=1)

    assert clock.as_snapshot()["lapsBeforeClock"] == 0
    assert clock.as_snapshot()["greenToFirstCrossingS"] == 2.8


# ---------------------------------------------------- 2. the lap he can see

def a_coordinator() -> RaceCoordinator:
    race = RaceCoordinator(None, fuel_per_lap_l=7.806)
    race.arm(None, PlanContext(car="huracan-gt3", track="daytona",
                               layout="road-course", race_laps=20))
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    return race


def a_daytona_lap(lap_num: int) -> SessionEvent:
    """One crossing with session 127's own counters on it.

    `laps_completed` = `lap_num` + 1 on all 20 rows of that race - GT7
    increments at the crossing, so at this instant it names the lap he is
    about to drive, which is the number on his screen.
    """
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(
        lap_num=lap_num, lap_time_ms=105_671, best_lap_ms=104_500,
        delta_ms=0, fuel_start=91.83, fuel_end=84.02, fuel_used=7.81,
        position=9, is_pit_lap=False, is_out_lap=False,
        laps_completed=lap_num + 1)})


def test_the_spoken_lap_is_the_one_on_his_screen():
    """*"Lap 2. 18 laps to go."* went out while GT7 displayed lap 3.

    Both halves are asserted deliberately. The lap number was wrong and the
    laps-to-go was right, so a fix that moved both would trade one complaint
    for a worse one: 18 really did remain after two crossings of a 20-lap
    race, and he took the flag on the count the app already had.
    """
    race = a_coordinator()
    race.handle(a_daytona_lap(1))
    race.handle(a_daytona_lap(2))

    said = orientation(race.state)
    assert said.startswith("Lap 3."), said
    assert "18 laps to go." in said, said


def test_the_app_keeps_counting_crossings_while_the_radio_counts_screens():
    """**Rule 13: two quantities, two names, and neither may be read as the
    other.** `state.lap` is what every piece of race arithmetic uses and it
    stays on the crossings behind him; `screen_lap` is the only one that may
    be spoken."""
    race = a_coordinator()
    race.handle(a_daytona_lap(1))
    race.handle(a_daytona_lap(2))

    assert race.state.lap == 2
    assert race.state.screen_lap == 3
    assert race.snapshot()["lap"] == 2
    assert race.snapshot()["screenLap"] == 3


def test_gt7s_own_count_beats_the_arithmetic_when_a_crossing_goes_missing():
    """The offset is not always one. Road Atlanta measured +1 on lap 1 and +2
    by lap 20, the crossing inside the pit sequence never reaching the app -
    so the number is taken from GT7 at every crossing rather than derived once
    and carried."""
    race = a_coordinator()
    race.handle(a_daytona_lap(1))
    event = a_daytona_lap(2)
    event.data["lap"].laps_completed = 4        # GT7 counted one the app lost
    race.handle(event)

    assert race.state.lap == 2
    assert orientation(race.state).startswith("Lap 4."), orientation(race.state)


# ------------------------------------------------------------ 3. the fuel

def lap_two_of_session_127(**overrides) -> RaceState:
    """The tank as it actually stood when `-7.1` was spoken.

    Lap 2 closed on 84.023 L; the race's own green-lap burn came out at
    7.795 L/lap; the approved plan was 11 + 9, so the box lap was nine laps
    away. Every figure off `laps` and `race_runs` for session 127.
    """
    fields = dict(lap=2, laps_total=20, fuel_l=84.023, fuel_per_lap_l=7.806,
                  stint_ends_on_lap=11, position=9,
                  plan_binding_constraint="fuel")
    fields.update(overrides)
    return RaceState(**fields)


def a_colour_line(state: RaceState) -> str:
    laps, reference = fuel_in_hand(state)
    call = ColourCalls(CHATTY).data_line(
        lap=state.lap, fuel_laps_in_hand=laps, fuel_reference=reference)
    assert call is not None
    return call.spoken()


def test_the_running_fuel_line_and_the_engineer_name_one_journey():
    """**Rule 13, asserted between the two mouths rather than inside one.**

    22:16:26 - *"1.9 spare to the stop."* 22:16:52 - *"-7.1 laps of fuel in
    hand to the flag."* Same lap, same tank, 26 s apart, 9.0 laps apart.
    Neither line is checked here against a formula; they are checked against
    each other, which is the property the driver actually needs and the one
    that failed.
    """
    state = lap_two_of_session_127()
    colour = a_colour_line(state)
    engineer = _fuel_standing(state)

    reference = fuel_reference(state)
    assert reference in colour, colour
    assert reference in engineer, engineer
    assert "to the flag" not in colour, colour


def test_the_fuel_in_hand_is_not_negative_with_a_full_tank_and_a_stop_to_come():
    """84.0 L aboard, 9 laps to the box, 10.8 laps of fuel in the tank. The
    old expression said **-7.1** because it counted 18 laps to the flag and
    none of the litres the planned stop would add. There is no reading of
    that race in which he was seven laps short on lap two."""
    laps, reference = fuel_in_hand(lap_two_of_session_127())

    assert reference == "to the stop"
    assert laps is not None and laps > 0, laps


def test_after_the_stop_the_flag_is_the_reference_and_the_number_is_the_one_that_was_right():
    """**The late calls were excellent and must not move.** Lap 16 said
    *"0.2 laps of fuel in hand to the flag"*; he took the flag with 1.444 L =
    0.185 laps. That call is this expression with no stop left to account
    for, which is why it was right, and it still reads 0.2 here."""
    state = lap_two_of_session_127(lap=16, fuel_l=32.689,
                                   stint_ends_on_lap=None)
    laps, reference = fuel_in_hand(state)

    assert reference == "to the flag"
    assert laps == 0.2
    assert "0.2 laps of fuel in hand to the flag." == a_colour_line(state)


def test_an_unmeasured_burn_still_names_what_it_could_not_tell_him():
    """Rule 3: missing is None, never zero - and the reference survives the
    missing number, because "I cannot tell you about the stop" and "I cannot
    tell you about the flag" are different silences."""
    laps, reference = fuel_in_hand(lap_two_of_session_127(fuel_per_lap_l=None))

    assert laps is None
    assert reference == "to the stop"
