"""Row 1.10: the rule-13 pass over the call inventory.

CLAUDE.md §4 rule 13 — *"Two calls that use the same words must mean the same
thing. 'Laps in hand' was spoken twice in two minutes meaning laps-to-the-stop
and laps-to-the-flag - figures ten laps apart, neither naming its reference.
Under a helmet the driver cannot ask which one he just heard."*

Twenty-eight call kinds, 51 `Call(...)` sites and about 239 distinct sentence
templates were walked. The two that would have cost him a race are here with
a test each; the rest are wording changes covered by the tests that already
pinned those sentences, and by `test_phrase_manifest` and `test_voice_pack`,
which is what row 1.10's "manifest diff" means in practice - a sentence that
moves and does not reach the pack is a pause at the moment a call arrives.
"""
from __future__ import annotations

import pytest

from pitcrew.race.calls import (BOX_NOW, RaceState, _box_now, fuel_in_hand,
                                fuel_reference)


@pytest.fixture()
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------ blocker one

def _short_on_fuel() -> RaceState:
    """Lap 8 of 20, boxing on 11, 30 L aboard against 5 L a lap."""
    return RaceState(lap=8, laps_total=20, stint_ends_on_lap=11,
                     fuel_l=30.0, fuel_per_lap_l=5.0,
                     plan_binding_constraint="fuel",
                     # The regulations are satisfied, so the fuel branch is
                     # the one that keeps the stop - which is the point.
                     mandatory_stops_left=0)


def test_the_fuel_answer_names_the_same_reference_the_call_does():
    """**The original rule-13 defect, reinstated on the push-to-talk path.**

    He asks "how's the fuel" and hears *"6.0 laps of fuel."* - `laps_of_fuel`,
    an absolute, tank over burn. Two laps later the engineer volunteers
    *"3.0 laps of fuel in hand to the stop."* - `_fuel_gap`, a margin. One
    noun phrase, two quantities, and the answer named no reference at all.

    The failure direction is the one that kills a race: 6.0 heard as a margin
    with ten laps to run means believing in slack that is really minus four.
    """
    from pitcrew.engineer.intents import FUEL, answer

    state = _short_on_fuel()
    gap, reference = fuel_in_hand(state)
    assert reference == fuel_reference(state), "one expression, both halves"
    said = answer(FUEL, {"fuelInHand": gap, "fuelReference": reference}).text
    assert said == f"{gap:.1f} laps of fuel in hand {reference}."
    assert "to the stop" in said or "to the flag" in said


def test_an_absolute_is_said_as_one_where_nothing_frames_it():
    """No stop and no flag to be a margin to - so the tank, said as the tank.
    "Laps of fuel" alone is the phrase the volunteered call uses for a
    margin, and it may not stand for an absolute."""
    from pitcrew.engineer.intents import FUEL, answer

    said = answer(FUEL, {"lapsOfFuel": 8.2}).text
    assert said == "8.2 laps of fuel in the tank."
    assert "in hand" not in said


# ------------------------------------------------------------ blocker two

def _fuelled_to_the_flag() -> RaceState:
    """Lap 8 of 20 with a fuel-bound stop planned at 11 and 60 L aboard
    against 3 L a lap: `_stops_off` has just said the stop is off."""
    return RaceState(lap=8, laps_total=20, stint_ends_on_lap=11,
                     fuel_l=60.0, fuel_per_lap_l=3.0,
                     plan_binding_constraint="fuel", mandatory_stops_left=0)


def test_a_cancelled_stop_stops_being_counted_down_everywhere_at_once():
    """**The first fix guarded two call sites and left four surfaces
    counting.**

    `_stops_off` says *"You're fuelled to the flag. No more stops on fuel."*
    and does not clear `stint_ends_on_lap`; `_box_now` and `_box_soon` go
    quiet because they gate on `stop_still_needed`. Everything else read the
    raw field: the driver board's box panel showed **3 · plan: lap 11** and
    went red inside two laps, the Race screen showed **BOX IN 3**, and the
    push-to-talk answered *"Box in 3 laps."* and *"LR 72 percent. 3 laps to
    the stop."* - all for a stop that had been called off.

    A guard at each consumer is four chances to miss one, and the first
    attempt missed all four. The retirement belongs in the expression they
    all read (rule 12) - and the only test on it was a grep of the source,
    which is why nothing noticed.
    """
    from pitcrew.race.calls import stop_still_needed

    state = _fuelled_to_the_flag()
    assert stop_still_needed(state) is False, "the stop is off"
    assert state.laps_to_stop() is None, "so nothing counts down to it"
    # And it comes back the moment the stop does.
    state.fuel_l = 6.0
    assert stop_still_needed(state) is True
    assert state.laps_to_stop() == 3


def test_every_surface_reads_the_one_expression():
    """The four that were missed, each traced to `laps_to_stop`."""
    from pitcrew.engineer.intents import BOX_WHEN, TYRES, answer

    state = _fuelled_to_the_flag()
    snapshot = {"lapsToStop": state.laps_to_stop(), "hasPlan": True,
                "wearWorst": 0.72, "wearCorner": "lr"}
    # The push-to-talk, both answers that carried the countdown.
    assert answer(BOX_WHEN, snapshot).text == "No stop planned. Running to the flag."
    assert answer(TYRES, snapshot).text == "LR 72 percent."
    # The Race screen and the driver board both read `lapsToStop` /
    # `laps_to_stop()` and render nothing where it is None.
    assert snapshot["lapsToStop"] is None


def test_the_countdown_describes_rather_than_instructing():
    """It is the commentary tier: "Stop next lap." is the box call's own
    words, arriving without the box call's evidence."""
    from pitcrew.race.colour import ColourCalls

    tier = ColourCalls()
    call = tier._countdown(lap=9, stint_ends_on_lap=10)
    assert call is not None and call.call == "One lap to the stop."
    call = tier._countdown(lap=7, stint_ends_on_lap=10)
    assert call is not None and call.call == "3 laps to the stop."


# ------------------------------------------- the box call names its reason

def test_the_routine_box_call_says_what_it_is_boxing_him_for():
    """Rule 12, and §5.5's own worked example. Of four calls that say "Box
    this lap", three named their cause - the stint limit, the gauge reading,
    the rival - and the routine one said *"Box this lap. Fuel to 68 litres -
    9 laps after the box."*, which is the fill instruction standing where the
    reason belongs. The decision came from `stop_still_needed`, which turns
    on `plan_binding_constraint`, and that word was never spoken."""
    state = _short_on_fuel()
    state.lap = 11                                    # the box lap
    call = _box_now(state)
    assert call is not None and call.kind == BOX_NOW
    assert call.reason.startswith("Fuel won't reach the flag.")


def test_a_plan_that_names_no_constraint_does_not_invent_one():
    state = _short_on_fuel()
    state.lap = 11
    state.plan_binding_constraint = None
    call = _box_now(state)
    assert call is not None
    assert "constraint" not in call.reason


# ------------------------------------------- the brief and the instrument

def test_the_brief_does_not_deny_a_wall_that_is_watching():
    """`brief.py`'s own rule, one line above the offending one, is that
    promising an instrument that is not there is worse than promising
    nothing. This was the same failure running backwards: the line was
    unconditional, and the engineer then volunteered "Boxhead has boxed on 40
    litres" and "Faster than Boxhead through 1 and 2" about cars he had
    opened the race by saying he could not see."""
    from pitcrew.race.brief import Instruments, brief

    watching = brief(Instruments(race_laps=20, sees_rivals=True))
    assert not any("can't see other cars" in line for line in watching)
    blind = brief(Instruments(race_laps=20, sees_rivals=False))
    assert any("can't see other cars" in line for line in blind)
    # Unknown is treated as blind: a brief promises less, never more.
    unsure = brief(Instruments(race_laps=20))
    assert any("can't see other cars" in line for line in unsure)


def test_the_brief_reads_the_condition_the_wall_actually_starts_on():
    """Asked before the wall is built - `_start_pit_wall` runs after the
    brief is spoken - so it is the condition that is read, not the object,
    and both come from one predicate (rule 12)."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parents[1] / "controller.py"
              ).read_text(encoding="utf-8")
    assert "def _wall_cannot_watch(self)" in source
    assert "sees_rivals=self._wall_cannot_watch() is None," in source


# ------------------------------- the reason comes from the branch that bound

def test_the_reason_names_the_branch_that_kept_the_stop():
    """Rule 12, and the first attempt got it wrong. `_stop_needed_on_fuel`
    returns True on three disjoint grounds and only one reads
    `plan_binding_constraint` - so with a mandatory stop owed and fuel good
    to the flag the driver heard *"Box this lap. Fuel is the constraint."*,
    which is the Fuji failure `binding_limit` exists to prevent, reinstated
    on the voice path."""
    from pitcrew.race.calls import _why_the_stop_stands

    state = _fuelled_to_the_flag()
    assert _why_the_stop_stands(state) is None, "nothing keeps it"

    state.mandatory_stops_left = 1
    assert _why_the_stop_stands(state) == "The regulations need a stop."

    # The plan's own word is a pre-race enum `adopt()` never refreshes, and
    # `evidence` - the case that matters most - is meaningless said aloud.
    state.mandatory_stops_left = 0
    state.plan_binding_constraint = "evidence"
    assert _why_the_stop_stands(state) == "On the plan."
    state.plan_binding_constraint = "tyre"
    assert _why_the_stop_stands(state) == "On the plan.", \
        "and it may not collide with the gauge's measured tyre call"

    state.plan_binding_constraint = "fuel"
    state.fuel_l = 6.0
    assert _why_the_stop_stands(state) == "Fuel won't reach the flag."


def test_unknown_regulations_are_not_spoken_as_a_regulation():
    """CLAUDE.md rule 3. `mandatory_stops_left is None` keeps the stop - the
    safe decision - and says nothing about regulations, because nobody told
    the app there were any."""
    from pitcrew.race.calls import _why_the_stop_stands

    state = _fuelled_to_the_flag()
    state.mandatory_stops_left = None
    assert _why_the_stop_stands(state) == "On the plan."


def test_the_two_fuel_clauses_each_name_their_reference():
    """**They were never contradictory** - "Fuel won't reach the flag" is
    against the flag and "Fuel is fine" is against the next stint, and
    neither named one. The first fix SUPPRESSED the reason to hide the
    collision, which threw away the branch that kept the stop and left a box
    call whose whole stated reason argued against boxing.

    And the test written for that fix set `mandatory_stops_left = 1`, so the
    reason took the regulation branch and the assertion never touched the
    case at all - vacuous, then unfalsifiable once the string it looked for
    stopped existing. This drives the fuel branch."""
    state = _fuelled_to_the_flag()          # regs satisfied, plan says fuel
    state.lap = 11
    state.laps_total = 40                   # 40 laps at 3 L: the tank cannot
    state.next_stint_laps = 8               # but it covers the next stint
    state.further_stop_planned = True
    call = _box_now(state)
    assert call is not None
    assert "Fuel won't reach the flag." in call.reason
    assert "the tank covers the next stint" in call.reason,         "both are true, and each says which distance it is about"


def test_an_unknown_burn_is_not_spoken_as_a_shortfall():
    """`fuel_reaches_flag` returns None for "cannot be known" - no burn on
    file, no fuel reading, and a timed race has no lap count until the clock
    resolves one. `is not True` folded that into "Fuel won't reach the
    flag.", a claim about arithmetic nobody had done (rules 3 and 5). The
    stop is still kept; the unknown costs a sentence, not a stop."""
    from pitcrew.race.calls import _why_the_stop_stands, stop_still_needed

    state = _fuelled_to_the_flag()
    state.lap = 11
    state.fuel_per_lap_l = None             # no burn measured yet
    assert _why_the_stop_stands(state) == "On the plan."
    assert stop_still_needed(state) is True, "and the stop stands"


# ------------------------------------------------ one pair of numbers, one pair of words

def test_the_tow_says_where_each_figure_is_measured_and_keeps_its_rate():
    """The first fix distinguished the two "seconds a lap" figures and
    dropped the rate from one of them: "costs 1.4 seconds of lap time" reads
    as a total, and over a ten-lap tow that is 1.4 s against 14 - understating
    in the direction that makes the tow look free."""
    from pitcrew.race.tow import TowTrade

    made = TowTrade(laps_held=5, saving_l_per_lap=0.6, saving_s_per_lap=0.3,
                    losing_s_per_lap=1.4, reference="the plan")
    spoken, _ = made.sentence("Boxhead")
    assert "0.3 seconds a lap at the pump" in spoken
    assert "1.4 seconds a lap slower" in spoken
    assert "at the stop" not in spoken, "one vocabulary for one pair"


# ------------------------------- the fifth surface, which had no test at all

def test_a_retired_stop_is_not_overdue_on_the_snapshot():
    """`lapsPastBox` was read off the raw field and became the fifth surface
    counting a cancelled stop - and the loudest, because the desk screen
    shows it in warning ink. It comes off `laps_to_stop()` now, and the
    blocker's fix had no test on either half."""
    from pitcrew.race.coordinator import PlanContext, RaceCoordinator
    from pitcrew.telemetry.session_state import EventKind, SessionEvent

    race = RaceCoordinator(
        {"stints": [{"laps": 10, "compound": "RM", "fuel_l": 60.0,
                     "start_lap": 1},
                    {"laps": 10, "compound": "RM", "fuel_l": 60.0,
                     "start_lap": 11}],
         "stops": 1, "pit_laps": [10], "binding_constraint": "fuel"},
        fuel_per_lap_l=3.0, mandatory_stops=0)
    context = PlanContext(car="x", track="Spa", layout=None, race_laps=20)
    assert race.arm(context, context)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    state = race.state
    state.lap, state.fuel_l = 13, 60.0        # three laps past a box lap of 10
    state.drop_stop_granted = True            # the desk let it go

    assert state.past_box_lap is True, "he is past the box lap"
    assert state.laps_to_stop() is None, "and the stop is not a stop"
    assert race.snapshot()["lapsPastBox"] is None,         "so nothing may call him overdue for it"


def test_the_race_screen_never_shows_a_retired_stop_as_late(qt_app):
    """The other half. Before the fix the screen showed OVERDUE / "3 LATE"
    in warning ink on the lap "You're fuelled to the flag." went out."""
    from pitcrew.ui.race_screen import RaceScreen

    screen = RaceScreen()
    screen.show_snapshot({"lap": 13, "lapsToStop": None, "lapsPastBox": 3})
    assert "LATE" not in screen.box_in.value.text().upper()
    assert "OVERDUE" not in screen.box_in.name.text().upper()
    # And the flag is not a countdown either.
    screen.show_snapshot({"lap": 20, "lapsToStop": 0, "finished": True})
    assert screen.box_in.name.text().upper() == "FLAG"
