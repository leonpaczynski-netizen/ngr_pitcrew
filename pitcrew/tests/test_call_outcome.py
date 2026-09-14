"""What followed a call, and the far larger set the app may not answer.

The log carried what was said, why and how sure, and nothing about what the
driver then did — so a call he acted on and a call he ignored read identically
afterwards. Those are the two that most need telling apart on this rig: he has
overruled the engineer and been right four sessions running.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.race.call_outcome import (
    ACTED,
    CANNOT_TELL,
    NOT_ACTED,
    outcome_for,
    summarise,
)
from pitcrew.race.calls import BOX_NOW, BOX_SOON, FUEL_SHORT, Call, TYRE_TEMP


@dataclass
class _Lap:
    lap_num: int
    is_pit_lap: bool = False
    short_shift_rpm: float | None = None


def a_race(count: int, *, pit_on: int | None = None,
           short_shift_on: int | None = None):
    return [_Lap(lap_num=n,
                 is_pit_lap=(n == pit_on),
                 short_shift_rpm=450.0 if n == short_shift_on else 0.0)
            for n in range(1, count + 1)]


def a_call(kind=BOX_NOW, lap=10, **kw):
    return Call(kind=kind, lap=lap, call="Box this lap or next.",
                reason="Fuel is the constraint.", **kw)


# ------------------------------------------------------------- box calls

def test_a_stop_inside_the_window_is_acted_on():
    outcome = outcome_for(a_call(lap=10), a_race(20, pit_on=11))
    assert outcome.verdict == ACTED
    assert "lap 11" in outcome.detail


def test_no_stop_in_a_fully_driven_window_is_not_acted_on():
    """**Not a judgement on the driver.** At Fuji he ignored two box calls,
    ran to the flag and finished P5, and the app's own binding-constraint
    figure was the thing that was wrong."""
    outcome = outcome_for(a_call(lap=10), a_race(20))
    assert outcome.verdict == NOT_ACTED
    # From the lap after the call: lap 10 was driven before it was said.
    assert "11-12" in outcome.detail


def test_a_stop_after_the_window_is_not_late_compliance():
    """"Box this lap or next" is the instruction. A stop three laps later is
    a different decision, and recording it as obedience would make the log
    agree with whatever happened."""
    assert outcome_for(a_call(lap=10), a_race(20, pit_on=14)).verdict == NOT_ACTED


def test_a_window_the_race_never_reached_says_so():
    """**The flag is not disobedience.** A box call on the last lap with two
    laps of window and none of them driven says nothing about the driver."""
    outcome = outcome_for(a_call(lap=19), a_race(20))
    assert outcome.verdict == CANNOT_TELL
    assert "never fully driven" in outcome.detail


def test_a_call_after_the_last_lap_on_file_is_unanswerable():
    outcome = outcome_for(a_call(lap=25), a_race(20))
    assert outcome.verdict == CANNOT_TELL


def test_box_soon_is_judged_the_same_way_as_box_now():
    assert outcome_for(a_call(kind=BOX_SOON, lap=5),
                       a_race(20, pit_on=6)).verdict == ACTED


# ------------------------------------------------------- the short-shift

def test_a_short_shift_is_not_answerable_the_beep_is_the_instruction():
    """**This file used to assert the opposite**, and it was a closed loop
    (critic pass 8, 8 Sep 2026). `laps.short_shift_rpm` is the APP's switch -
    `analysis/driving.py` says so in its first line - so the app set the beep
    when it made the call, every frame of the next lap wrote the drop back
    onto the lap, and judging on it asked whether the app did what the app
    did. A driver who ignored the call and shifted at the limiter all lap
    read ACTED. What would answer it is `laps.upshift_rpm`, measured off the
    frames, and it has no calibrated threshold."""
    call = a_call(kind=TYRE_TEMP, lap=8, short_shift_drop_rpm=450.0)
    outcome = outcome_for(call, a_race(20, short_shift_on=9))
    assert outcome.verdict == CANNOT_TELL and outcome.settled
    assert "STOP saving, not start" in outcome.detail
    # And the same where the beep was never engaged: the field is not about
    # him either way, so neither reading is evidence about the driver.
    assert outcome_for(call, a_race(20)).verdict == CANNOT_TELL


# ------------------------------------------- everything the feed cannot see

def test_a_stay_out_is_judged_on_the_stop_that_did_not_come():
    """Critic pass 8, fifth round. A stay-out fold carries
    `short_shift_drop_rpm`, so it fell into the short-shift branch and was
    refused for not knowing whether he short-shifted - answering a question
    the call never asked. What it asked was whether he stayed out, and
    `laps.is_pit_lap` says so: the box call's instrument, inverted."""
    from pitcrew.race.calls import STAY_OUT

    call = a_call(kind=STAY_OUT, lap=8, short_shift_drop_rpm=400.0)
    stayed = outcome_for(call, a_race(20))
    assert stayed.verdict == ACTED and "stayed out" in stayed.detail
    boxed = outcome_for(call, a_race(20, pit_on=9))
    assert boxed.verdict == NOT_ACTED and "boxed on lap 9" in boxed.detail
    # And it waits for its window like a box call does.
    assert outcome_for(call, a_race(9)).settled is False


def test_a_brake_balance_call_the_feed_cannot_confirm_says_so():
    """**GT7 broadcasts no brake balance.** Reporting a click as "not acted
    on" would turn a missing channel into a disobedient driver - a zero
    standing in for a measurement nobody took."""
    call = Call(kind=TYRE_TEMP, lap=10, call="Fronts heating.",
                reason="Up 4 on their normal. Brake balance one click "
                       "rearward.")
    outcome = outcome_for(call, a_race(20))
    assert outcome.verdict == CANNOT_TELL and outcome.settled
    assert "brake balance" in outcome.detail


# ------------------------------------------ the reason belongs to the kind

def test_no_refusal_names_a_channel_the_call_was_not_about():
    """Suzuka, 13 Sep 2026, race run 20: **every** call - the green, a
    place, an incident, a chase, a rival's stop, "two to go" - was written
    up as "nothing in the feed can confirm a <kind> of this kind - GT7
    broadcasts no fuel map and no brake balance". Not one of them was about
    the fuel map or the brake balance, and three of them were checkable
    against the laps on file."""
    from pitcrew.race.calls import (CHASE, GREEN, INCIDENT, POSITION,
                                    RIVAL_BOXED, STATUS)
    for kind, text in ((GREEN, "Green, green, green."),
                       (POSITION, "You're back on it."),
                       (INCIDENT, "Lap 2 is out."),
                       (STATUS, "Lap 4. 23 minutes left. P6."),
                       (TYRE_TEMP, "Tyres are up to temperature."),
                       (CHASE, "Car #6 5.7 ahead, 10 laps to go."),
                       (RIVAL_BOXED, "Car #16 has boxed on 33 litres.")):
        call = Call(kind=kind, lap=4, call=text, reason="")
        outcome = outcome_for(call, a_race(20), flagged=True)
        assert outcome.verdict == CANNOT_TELL, kind
        assert "fuel map" not in outcome.detail, kind
        assert "brake balance" not in outcome.detail, kind
        assert "of this kind" not in outcome.detail, kind


@dataclass
class _RaceLap:
    lap_num: int
    position: int = 5
    fuel_start: float = 50.0
    fuel_end: float = 43.0
    is_pit_lap: bool = False
    laps_dropped: int | None = None


def a_flagged_race(count: int, **per_lap):
    laps = [_RaceLap(lap_num=n) for n in range(1, count + 1)]
    for lap_num, fields in per_lap.items():
        for key, value in fields.items():
            setattr(laps[int(lap_num.lstrip("L")) - 1], key, value)
    return laps


def test_a_place_called_is_held_to_the_place_at_the_line():
    """`laps.position` is the place at the crossing that closed the lap the
    call was made in. The call is made mid-lap, `state.lap` counting the
    laps behind him, so a call on lap 8 is about lap 9's row."""
    from pitcrew.race.call_outcome import BORNE_OUT, NOT_BORNE_OUT
    from pitcrew.race.calls import POSITION

    call = Call(POSITION, 8, "P4 of 8.", "You've made a place.",
                position_called=4)
    held = outcome_for(call, a_flagged_race(14, L9={"position": 4}))
    assert held.verdict == BORNE_OUT and held.settled
    assert "P4" in held.detail and "lap 9" in held.detail
    # Suzuka lap 9: "P2 of 8" mid-lap, and the lap closed P5.
    call = Call(POSITION, 9, "P2 of 8.", "You've made 2 places.",
                position_called=2)
    lost = outcome_for(call, a_flagged_race(14, L10={"position": 5}))
    assert lost.verdict == NOT_BORNE_OUT and lost.settled
    assert "P5" in lost.detail and "P2" in lost.detail
    # **Not a claim that the place was never his**: a place held for eight
    # seconds and lost before the line is on file the same way.
    assert "before the line" in lost.detail


def test_a_place_waits_for_its_lap_and_refuses_an_unread_one():
    from pitcrew.race.calls import POSITION

    call = Call(POSITION, 8, "P4 of 8.", "", position_called=4)
    waiting = outcome_for(call, a_flagged_race(8))
    assert waiting.verdict == CANNOT_TELL and waiting.settled is False
    # Rule 3: `laps.position` defaults to 0, and a 0 is nobody's place.
    unread = outcome_for(call, a_flagged_race(9, L9={"position": 0}))
    assert unread.verdict == CANNOT_TELL and unread.settled
    assert "no place" in unread.detail


def test_a_rejoin_is_a_position_call_that_states_no_place():
    """"You're back on it." rides on the POSITION kind with no place in it,
    so there is nothing to hold to the line - and it must not be read as a
    place of 0."""
    from pitcrew.race.calls import POSITION

    call = Call(POSITION, 0, "You're back on it.",
                "About 5 seconds off the road.")
    outcome = outcome_for(call, a_flagged_race(14))
    assert outcome.verdict == CANNOT_TELL and outcome.settled
    assert "states no place" in outcome.detail


def test_laps_to_go_is_held_to_the_lap_the_flag_fell_on():
    """Suzuka: "Two to go." at the crossing that closed lap 13 claims laps
    14 and 15. The flag fell at the end of lap 14."""
    from pitcrew.race.call_outcome import BORNE_OUT, NOT_BORNE_OUT
    from pitcrew.race.calls import LAPS_TO_GO

    two = Call(LAPS_TO_GO, 13, "Two to go.", "On the clock.", tag="to-go-2")
    early = outcome_for(two, a_flagged_race(14), final=True, flagged=True)
    assert early.verdict == NOT_BORNE_OUT
    assert "lap 14" in early.detail and "one lap sooner" in early.detail
    right = outcome_for(two, a_flagged_race(15), final=True, flagged=True)
    assert right.verdict == BORNE_OUT and "lap 15" in right.detail
    last = Call(LAPS_TO_GO, 14, "Last lap.", "On the clock.", tag="to-go-1")
    assert outcome_for(last, a_flagged_race(15), final=True,
                       flagged=True).verdict == BORNE_OUT


def test_laps_to_go_needs_the_flag_not_just_the_last_row():
    """Before the flag the last lap on file is only the latest; ended with
    the Stop button it is not known to be the finishing lap at all."""
    from pitcrew.race.calls import LAPS_TO_GO

    two = Call(LAPS_TO_GO, 13, "Two to go.", "", tag="to-go-2")
    assert outcome_for(two, a_flagged_race(14)).settled is False
    stopped = outcome_for(two, a_flagged_race(14), final=True, flagged=False)
    assert stopped.verdict == CANNOT_TELL and stopped.settled
    assert "flag was never seen" in stopped.detail
    # A crossing the clock counted as missed moves every lap number after it.
    dropped = outcome_for(two, a_flagged_race(14, L14={"laps_dropped": 1}),
                          final=True, flagged=True)
    assert dropped.verdict == CANNOT_TELL and "missed" in dropped.detail


def test_fuel_short_to_the_flag_is_held_to_the_fuel_at_the_flag():
    """Suzuka: "3.0 laps short" on lap 1, no stop, and the flag taken on lap
    14 with 2.7 L aboard. **Not a verdict on the driver either way** - the
    call asked him to save, so the laps cannot say whether the projection
    was wrong or he did what he was told."""
    from pitcrew.race.call_outcome import BORNE_OUT, NOT_BORNE_OUT
    from pitcrew.race.calls import TO_THE_FLAG

    call = Call(FUEL_SHORT, 1, "Short-shift and lift into the slow corners.",
                "You're 3.0 laps short on fuel.", severity=3.0,
                fuel_frame=TO_THE_FLAG)
    assert outcome_for(call, a_flagged_race(14)).settled is False
    made_it = outcome_for(call, a_flagged_race(14, L14={"fuel_end": 2.73}),
                          final=True, flagged=True)
    assert made_it.verdict == NOT_BORNE_OUT and made_it.settled
    assert "2.7 L" in made_it.detail and "lap 14" in made_it.detail
    assert "cannot say which" in made_it.detail
    dry = outcome_for(call, a_flagged_race(14, L14={"fuel_start": 3.0,
                                                    "fuel_end": 0.0}),
                      final=True, flagged=True)
    assert dry.verdict == BORNE_OUT
    boxed = outcome_for(call, a_flagged_race(14, L8={"is_pit_lap": True}),
                        final=True, flagged=True)
    assert boxed.verdict == CANNOT_TELL and "boxed on lap 8" in boxed.detail


def test_fuel_short_refuses_where_its_frame_is_not_the_flag():
    from pitcrew.race.calls import TO_THE_STOP

    to_stop = Call(FUEL_SHORT, 3, "Short-shift 450.", "", severity=0.8,
                   fuel_frame=TO_THE_STOP)
    outcome = outcome_for(to_stop, a_flagged_race(14), final=True,
                          flagged=True)
    assert outcome.verdict == CANNOT_TELL and "to the stop" in outcome.detail
    unframed = Call(FUEL_SHORT, 3, "Short-shift 450.", "", severity=0.8)
    outcome = outcome_for(unframed, a_flagged_race(14), final=True,
                          flagged=True)
    assert outcome.verdict == CANNOT_TELL and outcome.settled
    unflagged = Call(FUEL_SHORT, 3, "Short-shift 450.", "",
                     fuel_frame="to the flag")
    assert outcome_for(unflagged, a_flagged_race(14), final=True,
                       flagged=False).verdict == CANNOT_TELL


def test_the_unanswerable_ones_are_counted_not_dropped():
    """A summary reading "2 acted, 1 not" over nine calls invites the reader
    to believe the app watched all nine."""
    calls = [a_call(lap=5), a_call(lap=10),
             a_call(kind=TYRE_TEMP, lap=12),
             a_call(kind=TYRE_TEMP, lap=13)]
    tally = summarise(calls, a_race(20, pit_on=6))
    assert tally[ACTED] == 1
    assert tally[NOT_ACTED] == 1
    assert tally[CANNOT_TELL] == 2
    assert sum(tally.values()) == len(calls)


def test_the_tally_counts_a_report_held_to_the_laps():
    from pitcrew.race.call_outcome import BORNE_OUT, NOT_BORNE_OUT
    from pitcrew.race.calls import POSITION

    calls = [Call(POSITION, 8, "P4 of 8.", "", position_called=4),
             Call(POSITION, 9, "P2 of 8.", "", position_called=2)]
    laps = a_flagged_race(14, L9={"position": 4}, L10={"position": 5})
    tally = summarise(calls, laps)
    assert tally[BORNE_OUT] == 1 and tally[NOT_BORNE_OUT] == 1
