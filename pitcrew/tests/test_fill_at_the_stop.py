"""The fill at the LAST stop is sized by the flag, never by the plan's stint.

Deep Forest, 6 Sep 2026, race_run 16. Plan: 11 + 10 on a 21-lap estimate of a
30-minute race. The stop came on lap 13; the clock had 7 laps left. With the
hose in George said "Fuel to 76 litres. 10 laps at this race's burn." - the
plan's second stint - and `fuel_target_l` had taken `max(next_stint_laps,
laps_after_this_stop)`, which can only RAISE the plan's figure. 70 L went in,
55-63 were needed, 19.73 L crossed the line: 9.9 s standing at 2 L/s, against
an 8 s gap to P2.

A `min()` would have been wrong the other way - an EARLY last stop has more
laps left than the stint says, and a stint-sized fill sends him out to run
dry. The rule is not a max or a min: with no further stop planned, the laps
still to run once the car leaves the box are the whole answer.
"""
from __future__ import annotations

import math

import pytest

from pitcrew.race.calls import (RaceState, _fuel_instruction, fuel_target_basis,
                                fuel_target_l)
from pitcrew.race.expectations import (FUEL_BASES_HEDGED,
                                       FUEL_BASIS_HIGHER_RACE,
                                       FUEL_BASIS_HIGHER_STINT,
                                       FUEL_BASIS_RACE,
                                       FUEL_BASIS_STINT)
from pitcrew.race.refuel import RefuelAdviser, RefuelWatch, TARGET


def deep_forest(**over):
    """Lap 13, in the box. The plan said 11 + 10; the clock says 7 to go."""
    fields = dict(lap=12, laps_total=20, fuel_per_lap_l=7.35, fuel_sd_l=0.25,
                  fuel_l=5.08, fuel_capacity_l=100.0,
                  next_stint_laps=10, further_stop_planned=False,
                  stint_ends_on_lap=11, laps_after_stops=8,
                  race_minutes=30.0, laps_estimate_firm=True, in_pit=True)
    fields.update(over)
    return RaceState(**fields)


def _laps(state: RaceState) -> float:
    return fuel_target_l(state) / state.fuel_per_lap_l


# ------------------------------------------------------------ the last stop

def test_a_late_last_stop_is_sized_by_the_laps_left_not_the_plan():
    """The P2 defect. 8 on the clock minus the lap in progress = 7 to run."""
    state = deep_forest()

    litres = fuel_target_l(state)

    assert litres is not None
    # Seven laps plus a margin - never the plan's ten.
    assert 7 * 7.35 <= litres < 8.5 * 7.35
    assert fuel_target_basis(state) == "7 laps after the box"


def test_an_early_last_stop_is_sized_by_the_laps_left_too():
    """Lap 9 of a 20-lap race with an 11 + 9 plan: 11 laps left, not 9."""
    state = deep_forest(lap=8, next_stint_laps=9, stint_ends_on_lap=11,
                        laps_after_stops=12, race_minutes=None)

    assert _laps(state) >= 11
    assert fuel_target_basis(state) == "11 laps after the box"


def test_a_plan_longer_than_the_race_cannot_size_the_fill():
    """21-lap plan, 20-lap race: the stint says 10, the clock says 7."""
    state = deep_forest(next_stint_laps=10, laps_after_stops=8)

    assert _laps(state) < 9
    assert "after the box" in fuel_target_basis(state)


def test_the_stint_still_sizes_an_intermediate_stop():
    """Stop 1 of a two-stop: the next stint, not the flag - a tankful nobody
    needs is the other failure, and it is why the plan's stint exists."""
    state = deep_forest(lap=6, next_stint_laps=7, further_stop_planned=True,
                        laps_after_stops=15)

    assert 7 * 7.35 <= fuel_target_l(state) < 8.5 * 7.35
    assert fuel_target_basis(state) == "the next 7-lap stint"


def test_a_hand_built_state_takes_the_plan_at_its_word():
    """`further_stop_planned` None is 'nobody said' - the old behaviour."""
    state = deep_forest(further_stop_planned=None, laps_after_stops=8)

    assert _laps(state) >= 10
    assert fuel_target_basis(state) == "the next 10-lap stint"


def test_no_stint_and_no_plan_falls_back_to_the_laps_remaining():
    state = deep_forest(next_stint_laps=None, stint_ends_on_lap=None,
                        laps_after_stops=None)

    laps_left = state.laps_remaining() - 1  # the lap the stop is on
    assert math.isclose(_laps(state), laps_left, abs_tol=1.5)
    assert fuel_target_basis(state) == f"{laps_left} laps after the box"


def test_the_box_call_names_the_bound_behind_the_litres():
    late = deep_forest()
    early = deep_forest(lap=8, next_stint_laps=9, laps_after_stops=12,
                        race_minutes=None)
    middle = deep_forest(lap=6, next_stint_laps=7, further_stop_planned=True,
                         laps_after_stops=15)

    assert _fuel_instruction(late).endswith("- 7 laps after the box.")
    assert _fuel_instruction(early).endswith("- 11 laps after the box.")
    assert _fuel_instruction(middle).endswith("- the next 7-lap stint.")


# --------------------------------------------------------- with the hose in

def _fill(watch: RefuelWatch, *, target, basis, burn_basis=FUEL_BASIS_STINT,
          burn_laps=None):
    """Three rising frames past the arming threshold, then the target call."""
    said = []
    for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
        call = watch.note(fuel, speed_kph=0.0, target_l=target,
                          fuel_per_lap_l=7.35, basis=basis,
                          burn_basis=burn_basis, burn_laps=burn_laps)
        if call is not None:
            said.append(call)
    return said


def test_the_in_box_sentence_carries_the_same_bound():
    said = _fill(RefuelWatch(), target=63.0, basis="7 laps to the flag")

    assert [c.kind for c in said] == [TARGET]
    assert said[0].call == "Fuel to 63 litres."
    assert said[0].reason.startswith("7 laps to the flag, at this race's burn.")


def test_without_a_basis_the_old_lap_count_is_still_said():
    said = _fill(RefuelWatch(), target=63.0, basis=None)

    assert said[0].reason.startswith("9 laps at this race's burn.")


@pytest.mark.parametrize("burn_basis", [FUEL_BASIS_STINT, FUEL_BASIS_RACE,
                                        FUEL_BASIS_HIGHER_RACE,
                                        FUEL_BASIS_HIGHER_STINT])
def test_every_installed_race_burn_is_this_races(burn_basis):
    said = _fill(RefuelWatch(), target=63.0, basis="7 laps to the flag",
                 burn_basis=burn_basis)

    assert said[0].reason.startswith("7 laps to the flag, at this race's burn.")


def test_a_practice_burn_is_named_as_practice():
    """Sardegna, 15 Sep 2026, session 179, race_run 24, 20:30:32.

    "Fuel to 97 litres. 17 laps after the box, at this race's burn." - over
    `build_inputs`' practice 5.586 L/lap. Every lap ran the plan's fuel-save
    short-shift, so the expectation tracker installed no race burn and
    `fuel_burn_basis` stayed None. Driven through the controller's own
    context, so the words and the number come out of one state."""
    from types import SimpleNamespace

    from pitcrew.controller import PitCrewController

    state = deep_forest(fuel_per_lap_l=5.586, fuel_burn_basis=None)
    assert state.fuel_burn_basis is None
    stub = SimpleNamespace(race=SimpleNamespace(running=True, state=state))
    context = PitCrewController._refuel_context(stub)
    assert context[1] == 5.586 and context[4] is None

    spoken = []
    adviser = RefuelAdviser(context=lambda: context, speak=spoken.append)
    for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
        adviser.note_frame(fuel, 0.0)

    assert [c.kind for c in spoken] == [TARGET]
    assert spoken[0].reason.startswith(
        f"{fuel_target_basis(state)[0].upper()}"
        f"{fuel_target_basis(state)[1:]}, at the practice burn.")
    assert "this race" not in spoken[0].spoken()

    # And the same state once the race's burn is installed says so.
    state.fuel_burn_basis = FUEL_BASIS_RACE
    spoken.clear()
    adviser = RefuelAdviser(context=lambda: PitCrewController._refuel_context(
        stub), speak=spoken.append)
    for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
        adviser.note_frame(fuel, 0.0)
    assert ", at this race's burn." in spoken[0].reason


def test_a_practice_burn_without_a_bound_names_practice_too():
    said = _fill(RefuelWatch(), target=63.0, basis=None, burn_basis=None)

    assert said[0].reason.startswith("9 laps at the practice burn.")


def test_a_caller_that_does_not_say_whose_burn_names_none():
    """Not told is not practice and not the race: no burn is named."""
    said = []
    watch = RefuelWatch()
    for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
        call = watch.note(fuel, speed_kph=0.0, target_l=63.0,
                          fuel_per_lap_l=7.35, basis="7 laps to the flag")
        if call is not None:
            said.append(call)
    assert said[0].reason.startswith("7 laps to the flag.")
    assert "burn" not in said[0].reason


def test_the_adviser_accepts_three_four_and_five_value_contexts():
    spoken = []
    for context in (lambda: (63.0, 7.35, None),
                    lambda: (63.0, 7.35, None, "7 laps to the flag"),
                    lambda: (63.0, 7.35, None, "7 laps to the flag", None)):
        adviser = RefuelAdviser(context=context, speak=spoken.append)
        for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
            adviser.note_frame(fuel, 0.0)
    assert len(spoken) == 3
    assert spoken[0].reason.startswith("9 laps.")
    assert spoken[1].reason.startswith("7 laps to the flag.")
    assert spoken[2].reason.startswith(
        "7 laps to the flag, at the practice burn.")


# ---------------------------------------------------- the replay of the night

@pytest.mark.parametrize("laps_after_stops, expect_low, expect_high", [
    (8, 7 * 7.35, 8.5 * 7.35),     # what the clock said on lap 13
    (9, 8 * 7.35, 9.5 * 7.35),     # a lap more on the clock
    (11, 10 * 7.35, 11.5 * 7.35),  # the plan's stint, when it is true
])
def test_the_figure_follows_the_clock_and_never_the_stale_stint(
        laps_after_stops, expect_low, expect_high):
    litres = fuel_target_l(deep_forest(laps_after_stops=laps_after_stops))
    assert expect_low <= litres < expect_high


# ------------------------------------- rule 4: how many laps is this burn?

def test_the_fill_call_says_how_many_laps_stand_behind_the_burn():
    """Bathurst Rd 8, 20 Sep 2026: "at this race's burn" meant nineteen laps
    of evidence on lap 25 and three laps on lap 26, in an identical sentence.
    All five bases collapse to four words (`refuel._burn_words`), so rule 4's
    sample count never reached the ear at all and rule 13 was broken between
    two calls a lap apart.

    Its own sentence, because `phrase_manifest._pieces` can only render a
    sentence with one number in it - folded into the burn clause the whole
    line would fall to live synthesis."""
    said = _fill(RefuelWatch(), target=63.0, basis="7 laps to the flag",
                 burn_laps=19)
    assert said[0].reason.startswith(
        "7 laps to the flag, at this race's burn. Measured over 19 laps.")

    thin = _fill(RefuelWatch(), target=63.0, basis="7 laps to the flag",
                 burn_laps=3)
    assert "Measured over 3 laps." in thin[0].reason


def test_one_lap_of_evidence_is_said_in_the_singular():
    said = _fill(RefuelWatch(), target=63.0, basis=None, burn_laps=1)
    assert "Measured over 1 lap." in said[0].reason


def test_the_practice_burn_gets_no_lap_count():
    """The plan's sample count is not a count of laps run today, and one form
    of words may not cover two quantities (rule 13)."""
    said = _fill(RefuelWatch(), target=63.0, basis=None, burn_basis=None,
                 burn_laps=30)
    assert "Measured over" not in said[0].reason
    assert said[0].reason.startswith("9 laps at the practice burn.")


def test_a_race_burn_with_no_count_says_nothing_extra():
    """Rule 3: missing is silence, never a zero and never a guess."""
    said = _fill(RefuelWatch(), target=63.0, basis=None, burn_laps=None)
    assert "Measured over" not in said[0].reason
    said_zero = _fill(RefuelWatch(), target=63.0, basis=None, burn_laps=0)
    assert "Measured over" not in said_zero[0].reason


def test_the_count_travels_through_the_adviser_context():
    """The sixth element of the controller's context tuple. A context too old
    to carry it names the burn without its count rather than inventing one."""
    spoken = []
    adviser = RefuelAdviser(
        context=lambda: (63.0, 7.35, None, "7 laps to the flag",
                         FUEL_BASIS_STINT, 19),
        speak=spoken.append)
    for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
        adviser.note_frame(fuel, 0.0)
    assert "Measured over 19 laps." in spoken[0].reason

    older = []
    adviser = RefuelAdviser(
        context=lambda: (63.0, 7.35, None, "7 laps to the flag",
                         FUEL_BASIS_STINT),
        speak=older.append)
    for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
        adviser.note_frame(fuel, 0.0)
    assert "Measured over" not in older[0].reason


# ------------------------------- rule 5: a derived basis is hedged, not counted

@pytest.mark.parametrize("hedged", list(FUEL_BASES_HEDGED))
def test_a_hedged_basis_is_hedged_and_never_given_a_sample_count(hedged):
    """A column burn is this race's OTHER beep column converted at the plan's
    ratio - a derived conversion, not a measured population - and "Measured
    over 19 laps." over it states a claim the evidence does not support, in
    the most confident form of words the call has (rule 5). The same goes for
    the two `HIGHER_*` bases: `calls` already speaks them at MEDIUM off
    `FUEL_BASES_HEDGED`, and this module was the one consumer not reading the
    tuple at all."""
    said = _fill(RefuelWatch(), target=63.0, basis="7 laps to the flag",
                 burn_basis=hedged, burn_laps=19)

    assert "Measured over" not in said[0].reason
    assert "19" not in said[0].reason
    # "Unconfirmed." is the word CLAUDE.md §5.5 says he can act on, and it is
    # `calls`' own LOW-confidence mark - already in the voice pack, so the
    # hedge costs no clip and is not a second vocabulary (rule 13).
    assert said[0].reason.endswith("Unconfirmed.")
    assert said[0].reason.startswith("7 laps to the flag, at this race's burn.")


def test_a_measured_basis_still_carries_its_count():
    """The hedge is for the derived bases only. A burn measured on the laps
    it describes keeps rule 4's sample count."""
    for basis in (FUEL_BASIS_STINT, FUEL_BASIS_RACE):
        said = _fill(RefuelWatch(), target=63.0, basis=None,
                     burn_basis=basis, burn_laps=19)
        assert "Measured over 19 laps." in said[0].reason
        assert "Unconfirmed" not in said[0].reason


def test_the_hedge_travels_through_the_controllers_own_context():
    """Not a hand-built lambda: the six-element tuple `_refuel_context`
    actually returns. The count reaching the adviser is what makes the hedge
    matter - before 21 Sep 2026 the producer returned five elements and no
    count arrived at all, so nothing here could have been wrong out loud."""
    from types import SimpleNamespace

    from pitcrew.race.expectations import FUEL_BASIS_COLUMN
    from pitcrew.controller import PitCrewController

    state = deep_forest(fuel_burn_basis=FUEL_BASIS_COLUMN,
                        fuel_burn_laps=19)
    stub = SimpleNamespace(race=SimpleNamespace(running=True, state=state))
    context = PitCrewController._refuel_context(stub)
    assert len(context) == 6 and context[4] == FUEL_BASIS_COLUMN
    assert context[5] == 19

    spoken = []
    adviser = RefuelAdviser(context=lambda: context, speak=spoken.append)
    for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
        adviser.note_frame(fuel, 0.0)
    assert spoken[0].reason.endswith("Unconfirmed.")
    assert "Measured over" not in spoken[0].reason

    # And the same state on a measured basis counts its laps.
    state.fuel_burn_basis = FUEL_BASIS_RACE
    spoken.clear()
    adviser = RefuelAdviser(
        context=lambda: PitCrewController._refuel_context(stub),
        speak=spoken.append)
    for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
        adviser.note_frame(fuel, 0.0)
    assert "Measured over 19 laps." in spoken[0].reason
