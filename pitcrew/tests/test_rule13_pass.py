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

from pitcrew.race.calls import (BOX_NOW, RaceState, _box_now, fuel_in_hand,
                                fuel_reference)


# ------------------------------------------------------------ blocker one

def _short_on_fuel() -> RaceState:
    """Lap 8 of 20, boxing on 11, 30 L aboard against 5 L a lap."""
    return RaceState(lap=8, laps_total=20, stint_ends_on_lap=11,
                     fuel_l=30.0, fuel_per_lap_l=5.0,
                     plan_binding_constraint="fuel")


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

def test_the_chatty_tier_stops_counting_down_to_a_cancelled_stop():
    """**The engineer cancels the stop and the commentary reinstates it.**

    `_stops_off` says *"You're fuelled to the flag. No more stops on fuel."*
    and does not clear `stint_ends_on_lap`; `_box_now` and `_box_soon` go
    quiet because they gate on `stop_still_needed`. The colour tier speaks on
    exactly the crossings where they are silent, and it counted from the raw
    field - so the next lap said *"Stop next lap."* in the box vocabulary,
    about a stop that had just been called off.

    The controller is where the two meet, so the fix is there: the figure
    comes from the expression that decided there is a stop (rule 12).
    """
    import pathlib

    source = (pathlib.Path(__file__).resolve().parents[1] / "controller.py"
              ).read_text(encoding="utf-8")
    # Both colour call sites, and neither passes the raw field.
    assert source.count("if stop_still_needed(state) else None") == 2
    assert "stint_ends_on_lap=state.stint_ends_on_lap," not in source
    assert "stint_ends_on_lap=state.stint_ends_on_lap)" not in source


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
    assert call.reason.startswith("Fuel is the constraint.")


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
