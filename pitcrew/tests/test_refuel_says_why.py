"""The box may not be silent, and it may not be silent about being silent.

Bathurst Rd 8, 20 Sep 2026, session 204, race_run 29. The in-box adviser was
reported as never having spoken at all. It had: `race_revisions` holds four of
its calls, all made with the hose in, all spoken -

    20:40:16  refuel-target   "Fuel to 52 litres. The next 6-lap stint, at
                               this race's burn."
    20:40:37  refuel-release  "Go. 51 litres aboard."
    21:04:31  refuel-target   "Fuel to 59 litres. The next 7-lap stint, at
                               this race's burn."
    21:04:56  refuel-short    "Save fuel from here. 9 litres light - about
                               1.1 laps."

- and `pitcrew.log` contains the word "refuel" exactly zero times for the whole
race. `voice._finish` writes "said ..." only when the caller handed `say` an
`on_done`, and `_voice_refuel` did not, so a working adviser and one that had
never been armed left exactly the same record. That is CLAUDE.md rule 10's
second half - log the accepts, not only the refusals - and this file holds it
to it.

The other half is the thing that WOULD have been undiagnosable. The watch
captures its target once, at the frame the fill is first seen, and a `None`
captured there used to be permanent: nothing could retire it, so a stop nobody
could size stayed mute for its whole minute and said nothing about why. A
`None` is not a figure that might wobble - it is "I have not been told" - so it
is taken again until a real one arrives, and if none ever does, the driver
hears the one instruction that needs no figure from this app (§5.4: GT7's own
diamond marker is accurate).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from pitcrew.race.calls import RaceState
from pitcrew.race.expectations import FUEL_BASIS_RACE
from pitcrew.race.refuel import (RELEASE, SHORT, TARGET, UNSIZED,
                                 UNSIZED_RISE_L, RefuelAdviser, RefuelWatch)


def _rising(start: float, litres: float, step: float = 0.5):
    """A fill: two flat frames to set the floor, then a climb."""
    fuels = [start, start]
    fuel = start
    while fuel < start + litres:
        fuel += step
        fuels.append(fuel)
    return fuels


# ---------------------------------------------- a stop nothing could size

def test_a_stop_nothing_could_size_says_so_rather_than_nothing():
    """The whole minute used to pass without a word, and silence in the box
    is indistinguishable from an app that has stopped."""
    watch = RefuelWatch()
    said = [c for c in
            (watch.note(f, speed_kph=0.0, target_l=None, fuel_per_lap_l=7.35)
             for f in _rising(5.0, UNSIZED_RISE_L + 3.0)) if c is not None]

    assert [c.kind for c in said] == [UNSIZED]
    assert said[0].call == "Fill to the diamond, plus a lap."
    assert said[0].reason == "I can't size this one."


def test_the_unsized_call_invents_no_litre_figure():
    """Rule 3. He is holding the refuelling trigger: a number this app made
    up is worse than no number, which is why it points at GT7's own."""
    watch = RefuelWatch()
    said = [c for c in
            (watch.note(f, speed_kph=0.0, target_l=None)
             for f in _rising(5.0, UNSIZED_RISE_L + 3.0)) if c is not None]

    assert not any(ch.isdigit() for ch in said[0].spoken()), said[0].spoken()


def test_the_unsized_call_waits_until_the_stop_is_really_a_stop():
    """Under `UNSIZED_RISE_L` aboard, nothing is said at all: a rise that
    small has not yet cost him anything to hear about."""
    watch = RefuelWatch()
    said = [c for c in
            (watch.note(f, speed_kph=0.0, target_l=None)
             for f in _rising(5.0, UNSIZED_RISE_L - 1.0)) if c is not None]

    assert said == []


def test_the_unsized_call_is_said_once_and_not_every_frame():
    watch = RefuelWatch()
    said = [c for c in
            (watch.note(f, speed_kph=0.0, target_l=None)
             for f in _rising(5.0, 60.0)) if c is not None]

    assert [c.kind for c in said] == [UNSIZED]


# ------------------------------------------------- the captured None, retired

def test_a_target_that_arrives_late_still_reaches_the_driver():
    """**Rule 10.** The target is captured once so it cannot wobble mid-fill,
    but a `None` captured once is a latch with nothing able to retire it -
    and it silenced the whole stop, in a module whose entire job is that
    minute. A figure arriving a second into the fill is taken."""
    watch = RefuelWatch()
    said = []
    # The fill arms with nothing able to size it...
    for fuel in _rising(5.0, 2.0):
        call = watch.note(fuel, speed_kph=0.0, target_l=None)
        if call is not None:
            said.append(call)
    assert said == []
    # ...and the race can size it a moment later.
    for fuel in _rising(7.0, 2.0)[2:]:
        call = watch.note(fuel, speed_kph=0.0, target_l=63.0,
                          fuel_per_lap_l=7.35, basis="7 laps to the flag",
                          burn_basis=FUEL_BASIS_RACE, burn_laps=9)
        if call is not None:
            said.append(call)

    assert [c.kind for c in said] == [TARGET]
    assert said[0].call == "Fuel to 63 litres."
    # And the words that qualify it came from the context that sized it, not
    # from the one that could not (rules 12, 13).
    assert said[0].reason.startswith(
        "7 laps to the flag, at this race's burn. Measured over 9 laps.")


def test_a_target_already_captured_is_never_replaced_mid_fill():
    """The other half of the same rule: a real figure is captured ONCE. The
    car is stationary for the whole fill, so a target that moved would be
    chatter, and the release is called against the number he was given."""
    watch = RefuelWatch()
    said = []
    for fuel in _rising(5.0, 2.0):
        call = watch.note(fuel, speed_kph=0.0, target_l=63.0,
                          fuel_per_lap_l=7.35)
        if call is not None:
            said.append(call)
    for fuel in _rising(7.0, 60.0)[2:]:
        call = watch.note(fuel, speed_kph=0.0, target_l=90.0,
                          fuel_per_lap_l=7.35)
        if call is not None:
            said.append(call)

    assert [c.kind for c in said] == [TARGET, RELEASE]
    assert said[0].call == "Fuel to 63 litres."
    assert said[1].reason == "63 litres aboard."


def test_the_diamond_is_superseded_by_a_figure_that_turns_up():
    """Said the diamond, then the race sized the stop. The litres win - he is
    still in the box and a real number beats a pointer to the gauge."""
    watch = RefuelWatch()
    said = []
    for fuel in _rising(5.0, UNSIZED_RISE_L + 2.0):
        call = watch.note(fuel, speed_kph=0.0, target_l=None)
        if call is not None:
            said.append(call)
    assert [c.kind for c in said] == [UNSIZED]
    for fuel in _rising(5.0 + UNSIZED_RISE_L + 2.0, 4.0)[2:]:
        call = watch.note(fuel, speed_kph=0.0, target_l=63.0,
                          fuel_per_lap_l=7.35, basis="7 laps to the flag")
        if call is not None:
            said.append(call)

    assert [c.kind for c in said] == [UNSIZED, TARGET]


# -------------------------------------------------------- rule 10: the log

def test_the_hose_going_in_is_logged_with_the_figure_that_sized_it(caplog):
    """The accept, not only the refusals. The number that sets the bar for
    everything this stop says never appeared in a log."""
    caplog.set_level(logging.INFO, logger="pitcrew.race")
    watch = RefuelWatch()
    for fuel in _rising(5.0, 3.0):
        watch.note(fuel, speed_kph=0.0, target_l=63.0, fuel_per_lap_l=7.35,
                   basis="7 laps to the flag", burn_basis=FUEL_BASIS_RACE,
                   burn_laps=9)

    armed = [r.getMessage() for r in caplog.records
             if "the hose is in" in r.getMessage()]
    assert len(armed) == 1
    assert "63.0 L" in armed[0]
    assert "7 laps to the flag" in armed[0]
    assert "this race's burn" in armed[0]
    assert "9" in armed[0]


def test_every_call_the_watch_makes_is_written_down(caplog):
    """Four calls were made at Bathurst and the log held none of them."""
    caplog.set_level(logging.INFO, logger="pitcrew.race")
    watch = RefuelWatch()
    for fuel in _rising(5.0, 60.0):
        watch.note(fuel, speed_kph=0.0, target_l=63.0, fuel_per_lap_l=7.35)

    said = [r.getMessage() for r in caplog.records if "[refuel-" in
            r.getMessage()]
    assert any("Fuel to 63 litres." in m and TARGET in m for m in said)
    assert any("Go." in m and RELEASE in m for m in said)


def test_a_stop_nobody_could_size_logs_which_half_was_missing(caplog):
    """"No target" has two causes and they are fixed in different places:
    nothing reached the watch at all, or a burn arrived with no lap count."""
    caplog.set_level(logging.INFO, logger="pitcrew.race")
    for burn, expect in ((7.35, "7.35 L/lap"),
                         (None, "no figure reached the watch at all")):
        caplog.clear()
        watch = RefuelWatch()
        for fuel in _rising(5.0, UNSIZED_RISE_L + 3.0):
            watch.note(fuel, speed_kph=0.0, target_l=None,
                       fuel_per_lap_l=burn)
        refused = [r.getMessage() for r in caplog.records
                   if "nothing sized this stop" in r.getMessage()]
        assert len(refused) == 1
        assert expect in refused[0]


def test_an_exit_that_says_nothing_says_why(caplog):
    """"He left and I said nothing" has four causes here and the log used to
    record none of them."""
    caplog.set_level(logging.INFO, logger="pitcrew.race")
    watch = RefuelWatch()
    assert watch.left_early(50.0) is None

    quiet = [r.getMessage() for r in caplog.records
             if "out of the box with nothing to say" in r.getMessage()]
    assert len(quiet) == 1
    assert "no fill was seen this stop" in quiet[0]


# ----------------------------------- through the controller's own producer

def _controller_stub(state):
    return SimpleNamespace(race=SimpleNamespace(running=True, state=state))


def test_a_stop_the_real_context_cannot_size_reaches_the_diamond_call():
    """**Not a hand-built tuple.** `PitCrewController._refuel_context` driven
    over a race whose lap count is not yet known - a timed race before the
    clock will commit to an estimate, which is the shape tonight's Monza race
    opens in with no prior data for the car. The burn is there; the laps to
    spend it on are not, so `fuel_target_l` returns None and the first
    element of the real tuple is None."""
    from pitcrew.controller import PitCrewController

    state = RaceState(lap=12, laps_total=None, fuel_per_lap_l=7.35,
                      fuel_capacity_l=100.0, in_pit=True)
    context = PitCrewController._refuel_context(_controller_stub(state))
    assert len(context) == 6
    assert context[0] is None and context[1] == 7.35

    spoken = []
    adviser = RefuelAdviser(
        context=lambda: PitCrewController._refuel_context(
            _controller_stub(state)),
        speak=spoken.append)
    for fuel in _rising(5.0, UNSIZED_RISE_L + 3.0):
        adviser.note_frame(fuel, 0.0)

    assert [c.kind for c in spoken] == [UNSIZED]
    assert spoken[0].spoken() == ("Fill to the diamond, plus a lap. "
                                  "I can't size this one.")


def test_the_real_context_sizing_it_late_still_reaches_the_driver():
    """The same race, once the clock commits to a lap count. Driven through
    the controller's own producer both times, so the figure and the words
    come out of one state."""
    from pitcrew.controller import PitCrewController

    state = RaceState(lap=12, laps_total=None, fuel_per_lap_l=7.35,
                      fuel_sd_l=0.25, fuel_capacity_l=100.0, in_pit=True,
                      fuel_burn_basis=FUEL_BASIS_RACE, fuel_burn_laps=9)
    stub = _controller_stub(state)
    spoken = []
    adviser = RefuelAdviser(
        context=lambda: PitCrewController._refuel_context(stub),
        speak=spoken.append)
    for fuel in _rising(5.0, 2.0):
        adviser.note_frame(fuel, 0.0)
    assert spoken == []

    state.laps_total = 20            # the clock commits, mid-fill
    for fuel in _rising(7.0, 4.0)[2:]:
        adviser.note_frame(fuel, 0.0)

    assert [c.kind for c in spoken] == [TARGET]
    assert "at this race's burn." in spoken[0].reason
    assert "Measured over 9 laps." in spoken[0].reason


# ---------------------------------------------- the call, once it is spoken

class _Voice:
    def __init__(self, played=True):
        self.played = played
        self.said = []

    def say(self, text, kind=None, on_done=None, keep=False):
        self.said.append((text, kind, on_done))
        if on_done is not None:
            on_done(self.played)


def _speaking_controller(voice):
    return SimpleNamespace(
        _engineer_speaks=True, voice=voice,
        ptt=SimpleNamespace(last_call=None), last_call=None,
        race_screen=None, race_run_id=None, race=None)


@pytest.mark.parametrize("played", [True, False])
def test_the_box_call_is_logged_as_heard_or_not(caplog, played):
    """The line that closes last night's question. `voice._finish` writes
    nothing at all for a caller that hands over no `on_done`, so four box
    calls spoken at Bathurst left the log looking exactly like an adviser
    that had never been armed."""
    from pitcrew.controller import PitCrewController
    from pitcrew.race.refuel import RefuelCall

    caplog.set_level(logging.INFO, logger="pitcrew.race")
    voice = _Voice(played=played)
    PitCrewController._voice_refuel(
        _speaking_controller(voice),
        RefuelCall(TARGET, "Fuel to 63 litres.", "7 laps to the flag."))

    assert voice.said[0][2] is not None, "no on_done: the voice logs nothing"
    booked = [r.getMessage() for r in caplog.records
              if "Fuel to 63 litres." in r.getMessage()]
    assert len(booked) == 1
    assert ("heard" in booked[0]) if played else ("NOT heard" in booked[0])
    assert TARGET in booked[0]


def test_a_silent_engineer_still_leaves_the_call_in_the_record(caplog):
    """Silent means silent, not idle (the controller's own words). The call
    was still made and the screen is the delivery - so the log says so."""
    from pitcrew.controller import PitCrewController
    from pitcrew.race.refuel import RefuelCall

    caplog.set_level(logging.INFO, logger="pitcrew.race")
    voice = _Voice()
    stub = _speaking_controller(voice)
    stub._engineer_speaks = False
    PitCrewController._voice_refuel(
        stub, RefuelCall(SHORT, "Save fuel from here.", "9 litres light."))

    assert voice.said == []
    assert any("Save fuel from here." in r.getMessage()
               and "the engineer is silent" in r.getMessage()
               for r in caplog.records)
