"""Declaring the instrument, so that silence means one thing afterwards."""
from __future__ import annotations

from pitcrew.race.brief import Instruments, brief, lost_the_gauge


def said(**over) -> str:
    fields = dict(has_plan=True, race_laps=26, stops=1,
                  compounds=("RH", "RS"), wear_gauge=True, temp_window=True)
    fields.update(over)
    return " ".join(brief(Instruments(**fields)))


def test_it_opens_with_the_shape_of_the_race():
    assert said().startswith("26 laps, 1 stop, RH onto RS.")


def test_it_always_ends_with_what_cannot_be_seen():
    """**The half he has no other way to learn.** There is no proximity or
    closing-speed channel in any packet format, so gaps, traffic and blue
    flags are not coming - and a driver who does not know that waits for them.
    """
    for lines in (brief(Instruments()), brief(Instruments(race_laps=20)),
                  brief(Instruments(race_minutes=50.0, wear_gauge=True))):
        assert lines[-1] == "I can't see other cars - position only."


def test_with_the_gauge_it_promises_the_gauge():
    assert "I have the tyre gauge this race." in said()


def test_without_it_the_silence_is_defined():
    """The sentence that makes every later silence honest."""
    lines = said(wear_gauge=False)
    assert "read it to me when you can" in lines
    assert "means I can't see them, not that they're fine" in lines


def test_a_timed_race_is_declared_as_a_clock_and_promises_no_lap_count():
    """**The correction that came out of review.** `laps_estimate_firm` rests
    on a lap-time spread that does not exist until several clean laps have run,
    so a lap count promised on the grid would have to be withdrawn - which is
    worse than never promising it. All three Monza races are timed.
    """
    lines = said(race_laps=None, race_minutes=50.0)
    assert "50 minutes, 1 stop - this one runs to the clock." in lines
    assert "won't give you a lap count until I can stand behind one" in lines
    assert " to go" not in lines


def test_no_plan_says_what_it_will_still_do():
    """Not "no plan" and then silence - what is left is fuel, and fuel is the
    lowest-noise channel in the app."""
    lines = brief(Instruments(has_plan=False))
    assert any("I'll call fuel and nothing else" in line for line in lines)


def test_a_missing_temperature_window_is_declared_not_invented():
    """No published GT7 optimum window exists, for anyone. A car with no
    measured window gets the trend and never a target number."""
    assert "call the trend and not a number" in said(temp_window=False)
    assert "trend and not a number" not in said(temp_window=True)


def test_a_stream_with_no_surface_channel_says_so():
    """The `A` packet format carries no per-wheel surface, so nothing can see
    a kerb or an off. One line, because it silences a whole family of calls."""
    assert "I can't see kerbs or offs" in said(surface_channel=False)
    assert "kerbs or offs" not in said(surface_channel=True)


def test_losing_the_gauge_mid_race_is_said_out_loud():
    """The brief promised an instrument. Losing it quietly would leave him
    reading the same silence as "tyres are fine" - the exact confusion the
    brief exists to remove."""
    assert "lost the tyre gauge" in lost_the_gauge()


def test_a_no_stop_race_says_no_stop_rather_than_nothing():
    """And still names the set, because a one-stint race is still run on
    something."""
    assert "26 laps, no stop, on RH." in said(stops=0, compounds=("RH",))


def test_the_brief_is_never_empty():
    """Even knowing nothing, there is something to declare."""
    assert brief(Instruments())


def test_a_repeated_compound_is_said_once():
    """"RM onto RM onto RM onto RM" is four facts where there is one. What he
    needs is the sequence of changes, and a stop that puts the same set back is
    not one."""
    assert "20 laps, 3 stops, on RM." in " ".join(
        brief(Instruments(has_plan=True, race_laps=20, stops=3,
                          compounds=("RM",) * 4, wear_gauge=True,
                          temp_window=True)))


def test_a_genuine_change_is_still_spelled_out():
    assert "onto RS" in said(compounds=("RH", "RH", "RS"))
