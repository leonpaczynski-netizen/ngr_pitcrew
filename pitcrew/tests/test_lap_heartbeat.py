"""The per-lap confirmation, and everything it must not quietly cost.

*"George should walk me through the race following the plan, each lap making
sure I'm on track"* - the driver, 28 Aug 2026. He chose a short confirmation
every lap over silence-unless-off-plan.

**It is the heartbeat with a rate on it, not a second call kind.**
`RaceState.record` sets `last_said_lap` for every kind, so a per-lap call of
any kind takes `laps_since_anything_said()` to 1 for the rest of the race -
which kills `_status` itself, the saving answer and the colour calls (both
reached only through the "nothing was said" branch), and clears the
short-shift beep the lap after it was asked for. One kind with a rate does
what he asked and none of that.

**And two of its three clauses had to be thrown away.** "On plan" is heard as
a lap-time claim, and lap time is not detectable here - measured sigma is
0.68-2.04 s against a 0.5-1.5 s/lap degradation band, so a pace verdict said
once is a bad call and said twenty times is twenty of them. "Fuel good" with
no noun after it is worse: `_fuel_target` returns laps-to-the-stop while a
stop is still to come and laps-to-the-flag once the box lap has gone by, so
the same two words mean figures ten laps apart on either side of one crossing.
That is rule 13, which is on file from a race where it happened by accident.
"""
from __future__ import annotations

from pitcrew.race.calls import (
    STATUS,
    STATUS_EVERY_LAPS,
    TO_THE_FLAG,
    TO_THE_STOP,
    RaceState,
    _status,
    fuel_reference,
    next_call,
)


def a_state(**overrides) -> RaceState:
    fields = dict(lap=7, laps_total=20, fuel_l=40.0, fuel_per_lap_l=3.4,
                  position=3, stint_ends_on_lap=13, next_compound="RM",
                  laps_since_stop=5, last_said_lap=6, status_every_laps=1)
    fields.update(overrides)
    return RaceState(**fields)


# ------------------------------------------------------------------ the rate

def test_at_the_every_lap_setting_it_speaks_every_lap():
    assert _status(a_state()) is not None


def test_the_default_is_still_the_five_lap_heartbeat():
    quiet = a_state(status_every_laps=STATUS_EVERY_LAPS, last_said_lap=6)
    assert _status(quiet) is None, "spoke four laps early"
    assert _status(a_state(status_every_laps=STATUS_EVERY_LAPS,
                           last_said_lap=2)) is not None


def test_it_never_displaces_a_real_call():
    """Lowest in `URGENCY`, and the fuel call has something to say here."""
    short = a_state(fuel_l=3.0)
    call = next_call(short)
    assert call is not None and call.kind != STATUS


# --------------------------------------------------------- the named reference

def test_the_reference_is_the_stop_while_a_stop_is_still_to_come():
    assert fuel_reference(a_state(lap=7, stint_ends_on_lap=13)) == TO_THE_STOP
    assert TO_THE_STOP in _status(a_state()).call


def test_the_reference_becomes_the_flag_once_the_box_lap_has_gone_by():
    """**The rule-13 crossing.** `_fuel_target` switches here, so the words
    have to switch with it or "fuel good" means two things in one race."""
    past = a_state(lap=14, stint_ends_on_lap=13)
    assert fuel_reference(past) == TO_THE_FLAG
    assert TO_THE_FLAG in _status(past).call


def test_every_fuel_sentence_names_what_it_is_measured_against():
    for state in (a_state(), a_state(fuel_l=8.0), a_state(fuel_l=90.0),
                  a_state(lap=14, stint_ends_on_lap=13)):
        call = _status(state)
        if call is None or "fuel" not in call.call.lower():
            continue
        assert TO_THE_STOP in call.call or TO_THE_FLAG in call.call, \
            f"unreferenced fuel claim: {call.call!r}"


# ------------------------------------------------------------- honest silence

def test_no_burn_figure_is_said_out_loud_and_never_as_good():
    """`laps_of_fuel` is None until a burn exists. Rendering that as "fuel
    good" is §4.3 wearing a sentence - a confident, well-formed answer no
    listener can tell from a real one."""
    call = _status(a_state(fuel_per_lap_l=None))
    assert call is not None
    assert "No burn figure yet" in call.call
    assert "good" not in call.call.lower()


def test_it_says_nothing_about_pace_in_any_state():
    """Pace is below the detection floor and the phrase he must never hear is
    the one that implies it has been checked."""
    for state in (a_state(), a_state(fuel_l=8.0), a_state(fuel_per_lap_l=None),
                  a_state(lap=14, stint_ends_on_lap=13)):
        call = _status(state)
        if call is None:
            continue
        said = call.call.lower()
        for banned in ("on plan", "pace", "lap time", "seconds a lap"):
            assert banned not in said, f"{banned!r} in {call.call!r}"


# ------------------------------------------------------------------- the guards

def test_it_is_quiet_in_the_pit_lane_and_after_the_flag():
    assert _status(a_state(in_pit=True)) is None
    assert _status(a_state(finished=True)) is None
    assert _status(a_state(lap=0)) is None


def test_it_is_quiet_before_the_engineer_has_ever_spoken():
    """`last_said_lap` of None is a race that has not started, not one that
    has gone quiet."""
    assert _status(a_state(last_said_lap=None)) is None


# ------------------------------------- what the heartbeat must not take from us

def test_the_saving_answer_still_gets_its_lap():
    """**The loop the engineer opens when he asks for a saving.**
    `_saving_response` is reached only when nothing else won the crossing, and
    at the every-lap setting the heartbeat wins almost all of them - so ranked
    on urgency alone it would close that loop forever, silently. The
    coordinator's own words: an unclosed loop leaves the driver believing a
    shortfall was covered when it was not."""
    from pitcrew.race.coordinator import RaceCoordinator

    race = RaceCoordinator({"stints": [{"laps": 20, "compound": "RM",
                                        "fuel_l": 60.0, "start_lap": 1}]})
    race.state.status_every_laps = 1
    race.state.last_said_lap = 1
    race.state.lap = 5
    race.state.laps_total = 20
    # Comfortably fuelled and mid-stint: nothing real is due, so the lap is
    # the heartbeat's to take - which is exactly the contest under test.
    race.state.fuel_l = 60.0
    race.state.fuel_per_lap_l = 3.4
    race.state.stint_ends_on_lap = 20
    race.state.position = 3
    race._saving_asked_lap = 1
    race._saving_answered = False
    race._saving_response = lambda: __import__(
        "pitcrew.race.calls", fromlist=["Call"]).Call(
            "saving-response", 5, "That's the saving. Hold it.", "")

    call = race._emit()
    assert call is not None and call.kind == "saving-response", \
        f"the heartbeat took the lap the saving answer needed: {call}"


def test_a_heartbeat_does_not_withdraw_a_short_shift_instruction():
    """The controller clears the beep on any call that does not ask for one -
    `None` there means "stop short-shifting". At the every-lap setting the
    heartbeat lands on the crossing after almost every real call, so without
    an exemption it withdraws the instruction the lap after it was given,
    every time, without a word."""
    import inspect

    from pitcrew import controller

    source = inspect.getsource(controller.PitCrewController._on_race_event)
    assert "if call.kind != STATUS:" in source, \
        "the heartbeat must not reach set_short_shift"
