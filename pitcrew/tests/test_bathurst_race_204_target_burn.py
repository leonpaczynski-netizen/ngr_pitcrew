"""Bathurst Rd 8, session 204: 28 laps judged against a burn 22% wrong.

Ford Shelby GT350R at Mount Panorama, 20 Sep 2026, strategy 38 - "3 stops,
fuel-bound", costed at **10.625 L/lap**. The driver decided at the last minute
to race **fuel map 3** for throttle stability, and the race burned 8.2-8.5.
His words: *"You could not have known this."* He is right, and that is the
point - the app's job is not to predict the decision, it is to absorb it.

The fuel *arithmetic* did absorb it: `burn installed on lap 7: 8.470 L/lap`,
and every fuel quantity from there on was sized on the race's own figure. The
**per-lap target** did not, and could not:

    grep -o "against [0-9.]* L$" logs/pitcrew.log | sort | uniq -c
    ->  22 against 10.625 L      (one distinct value, all race)

`PlanTargets.burn_full_l` was set in `__init__` and in `from_plan`, read in
`for_lap`, and had **no setter anywhere in `pitcrew/`**. So "Burn 2.2 litres
under" on lap 25 was not a verdict about lap 25; it restated the plan's error,
in the same four words it had used on lap 2 when it meant something else
(rule 13). Rule 10: a reference that disagrees with everything is the thing
that is wrong.

Every lap below is `laps` for session 204, read off `data/pitcrew.db`
verbatim, and the plan is `strategies` id 38 as approved.
"""
from __future__ import annotations

import logging

import pytest

from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.race.targets import burn_sentence, verdict_sentence
from pitcrew.strategy.targets import (BURN_BASIS_PLAN, BURN_BASIS_RACE,
                                      PlanTargets)
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent

# The plan's burn. Weighted median over 30 counted laps and six sessions, on
# map 1 - though nothing on the plan can say so, because `fuel_burns` has no
# map axis.
PLANNED_BURN = 10.625

# `lap_num: (lap_time_ms, fuel_start, fuel_end, fuel_used, pit, out, position)`
LAPS = {
    1: (135603, 49.98375, 91.32552, 0.0, 0, 0, 5),
    2: (128566, 91.32552, 83.02399, 8.301537, 0, 0, 3),
    3: (128797, 83.02399, 74.88139, 8.142593, 0, 0, 3),
    4: (127531, 74.88139, 66.43348, 8.447914, 0, 0, 1),
    5: (149865, 66.43348, 57.94233, 8.491150, 0, 0, 5),   # an off: 19% slow
    6: (127777, 57.94233, 49.43702, 8.505314, 0, 0, 5),
    7: (126882, 49.43702, 40.80255, 8.634468, 0, 0, 5),
    8: (126499, 40.80255, 32.33509, 8.467461, 0, 0, 5),
    9: (127480, 32.33509, 24.11610, 8.218988, 0, 0, 5),
    10: (127263, 24.11610, 16.22212, 7.893980, 0, 0, 4),
    11: (143636, 16.22212, 8.36498, 7.857139, 1, 0, 3),
    12: (175079, 8.36498, 91.87375, 7.941231, 0, 1, 5),
    13: (125974, 91.87375, 83.45668, 8.417068, 0, 0, 4),
    14: (127764, 83.45668, 74.84827, 8.608406, 0, 0, 4),
    15: (125810, 74.84827, 66.69033, 8.157944, 0, 0, 4),
    16: (128277, 66.69033, 58.26883, 8.421505, 0, 0, 4),
    17: (126314, 58.26883, 49.93983, 8.328995, 0, 0, 2),
    18: (125538, 49.93983, 41.90795, 8.031883, 0, 0, 2),
    19: (126020, 41.90795, 33.77855, 8.129395, 0, 0, 2),
    20: (125314, 33.77855, 25.42547, 8.353086, 0, 0, 2),
    21: (127149, 25.42547, 17.27157, 8.153893, 0, 0, 1),
    22: (141994, 17.27157, 9.69666, 7.574911, 1, 0, 2),
    23: (148824, 9.69666, 42.22735, 7.589315, 0, 1, 2),
    24: (127108, 42.22735, 34.34911, 7.878242, 0, 0, 2),
    25: (125922, 34.34911, 25.94343, 8.405678, 0, 0, 2),
    26: (125717, 25.94343, 17.69541, 8.248016, 0, 0, 2),
    27: (124992, 17.69541, 9.49911, 8.196300, 0, 0, 2),
    28: (126700, 9.49911, 1.53709, 7.962024, 0, 0, 2),
}

PLAN = {
    "stops": 3, "pit_laps": [8, 14, 21], "laps": 28, "max_race_laps": 28,
    "binding_constraint": "fuel",
    "fuel_burns": {"full": PLANNED_BURN},
    "stints": [
        {"laps": 8, "compound": "RS", "fuel_l": 95.3, "start_lap": 1},
        {"laps": 6, "compound": "RS", "fuel_l": 73.8, "start_lap": 9,
         "tyres": False},
        {"laps": 7, "compound": "RS", "fuel_l": 84.5, "start_lap": 15,
         "tyres": True},
        {"laps": 7, "compound": "RS", "fuel_l": 84.5, "start_lap": 22,
         "tyres": False},
    ],
    "targets": {
        "compounds": {"RS": {
            "lap_time_ms": 124773, "lap_time_ms_source": "author",
            "save_lap_time_ms": None, "save_lap_time_ms_source": "practice",
            "wear_per_lap": 0.0508, "wear_per_lap_source": "author",
            "reference_load_l": 40.0, "reference_load_l_source": "author"}},
        "fuel_weight_s_per_l_per_lap": 0.003,
    },
    "expects": {"expected_fuel_per_lap_l": PLANNED_BURN,
                "expected_fuel_samples": 30,
                "expected_lap_time_ms": 125897},
}


def lap_event(lap_num: int) -> SessionEvent:
    ms, start, end, used, pit, out, position = LAPS[lap_num]
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(
        lap_num=lap_num, lap_time_ms=ms, best_lap_ms=124_992,
        delta_ms=ms - 124_992, fuel_start=start, fuel_end=end,
        fuel_used=used, position=position,
        is_pit_lap=bool(pit), is_out_lap=bool(out))})


def a_race() -> RaceCoordinator:
    race = RaceCoordinator(
        PLAN, fuel_per_lap_l=PLANNED_BURN, fuel_capacity_l=100.0,
        lap_time_ms=125_897, practice_lap_samples=30, practice_fuel_samples=30)
    assert race.arm(None, PlanContext(
        car="Ford Shelby GT350R '16", track="Mount Panorama Circuit",
        layout="Full Course", race_laps=28)) is True
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 28}))
    return race


def drive(race: RaceCoordinator, through: int, *, start: int = 1) -> None:
    for lap_num in range(start, through + 1):
        race.handle(lap_event(lap_num))


# ------------------------------------------- the target follows the race burn

def test_the_target_burn_starts_on_the_plans_figure_and_says_so():
    """Before a race burn exists there is nothing else to judge against, and
    the verdict has to name which figure it used even then."""
    race = a_race()
    drive(race, 3)
    target = race.state.lap_target
    assert target.burn_l == pytest.approx(PLANNED_BURN)
    assert target.burn_source == BURN_BASIS_PLAN
    assert target.burn_laps is None, "the plan's figure has no laps of today"
    assert target.planned_burn_l == pytest.approx(PLANNED_BURN)


def test_the_target_burn_re_bases_when_the_race_burn_installs():
    """The headline. On the real race this stayed at 10.625 to the flag.

    The figure it moves to is the one already sizing the fill and the box
    call - `RaceState.fuel_per_lap_l` - so the two cannot disagree (rule 12).
    """
    race = a_race()
    drive(race, 7)
    assert race.state.fuel_burn_basis is not None, "the race burn installed"
    target = race.state.lap_target
    assert target.burn_source == BURN_BASIS_RACE
    assert target.burn_l == pytest.approx(race.state.fuel_per_lap_l)
    assert target.burn_l == pytest.approx(8.45, abs=0.2)
    # Rule 4: the sample count travels with the figure.
    assert target.burn_laps == race.state.fuel_burn_laps >= 5
    # And the plan's own number is still readable, never overwritten.
    assert target.planned_burn_l == pytest.approx(PLANNED_BURN)
    assert race.targets.burn_full_l == pytest.approx(PLANNED_BURN)


def test_the_last_lap_is_judged_against_the_race_and_not_the_plan():
    """Lap 28 burned 7.962. Against 10.625 that is "2.7 litres under" - a
    restatement of the plan's error. Against the race's own ~8.3 it is a
    verdict about lap 28."""
    race = a_race()
    drive(race, 28)
    verdict = race.state.target_verdict
    assert verdict is not None and verdict.lap == 28
    assert verdict.burn_source == BURN_BASIS_RACE
    assert abs(verdict.burn_delta_l) < 1.0, "not the 2.7 the plan would give"
    assert verdict.planned_burn_l == pytest.approx(PLANNED_BURN)
    # The sentence he hears names the reference, every time.
    said = verdict_sentence(verdict)
    assert "Against this race's burn." in said


def test_the_burn_clause_names_its_reference_in_both_registers():
    """Rule 13: two calls in the same words must mean the same thing. These
    are two references for one quantity, so they are two sentences."""
    assert burn_sentence(-2.2, BURN_BASIS_PLAN) == (
        "Burn 2.2 litres under. Against the plan.")
    assert burn_sentence(-2.2, BURN_BASIS_RACE) == (
        "Burn 2.2 litres under. Against this race's burn.")
    assert burn_sentence(0.0, BURN_BASIS_RACE) == (
        "Burn on target. Against this race's burn.")
    # A caller that did not say names nothing, rather than guessing.
    assert burn_sentence(-2.2) == "Burn 2.2 litres under."


def test_the_rebasing_is_logged_once_with_both_figures(caplog):
    """Rule 10's second half: log the accepts, not only the refusals. The
    ratchet was invisible for a whole race because the number setting the bar
    never appeared in the log."""
    caplog.set_level(logging.INFO, logger="pitcrew.race")
    race = a_race()
    drive(race, 28)
    lines = [r.getMessage() for r in caplog.records
             if "target burn re-based" in r.getMessage()]
    assert len(lines) == 1, "said once, not on every crossing"
    assert "the plan's 10.625 L/lap" in lines[0]
    # And every per-lap line now says which burn it was against.
    judged = [r.getMessage() for r in caplog.records
              if r.getMessage().startswith("target: lap 28 ")]
    assert judged and "this race's burn" in judged[0]


def test_the_stint_average_does_not_span_two_references():
    """A delta against 10.625 and one against 8.47 are not one population -
    pooling them lands between two references and belongs to neither."""
    race = a_race()
    drive(race, 6)
    assert race.state.stint_burns, "laps 2-4 and 6 were judged on the plan"
    drive(race, 7, start=7)
    # **Empty, and that is the honest answer.** Lap 7 is judged while the
    # plan's 10.625 is still the reference - it has to be, because a lap must
    # be judged against a figure older than itself, and the rebase runs after
    # the verdict for exactly that reason. So lap 7's delta is a plan-based
    # delta and is retired with the other four when 8.47 goes in. Nothing on
    # file is against the new reference until a lap has been DRIVEN under it,
    # which is lap 8.
    #
    # This asserted 1 while the rebase ran before the verdict, and that 1 was
    # the defect: laps 8, 13 and 26 of the s204 fixture came back at exactly
    # 0.000 - "burn on target" - because the target was that very lap, its own
    # burn having joined the population at `expect.note_lap` moments earlier.
    assert len(race.state.stint_burns) == 0
    drive(race, 8, start=8)
    assert len(race.state.stint_burns) == 1, "lap 8 is the first on 8.47"
    assert race.state.stint_burns[0] != 0.0, (
        "a lap judged against a reference containing itself reads 0.000")


# ------------------------------------------------ rule 10: it can be retired

def test_the_measured_burn_can_be_withdrawn():
    """A reference nothing can clear is the ratchet. `None` puts the target
    straight back on the plan's figure."""
    targets = PlanTargets.from_plan(PLAN)
    assert targets.install_measured_burn(8.47, laps=6, basis="the race")
    assert targets.for_lap(compound="RS", saving=False, lap_on_set=2,
                           fuel_at_start_l=40.0).burn_source == BURN_BASIS_RACE
    assert targets.install_measured_burn(None)
    back = targets.for_lap(compound="RS", saving=False, lap_on_set=2,
                           fuel_at_start_l=40.0)
    assert back.burn_source == BURN_BASIS_PLAN
    assert back.burn_l == pytest.approx(PLANNED_BURN)


@pytest.mark.parametrize("burn,laps", [(0.0, 5), (-1.0, 5), (8.4, 0),
                                       (None, 5), (8.4, None)])
def test_a_burn_with_nothing_behind_it_is_refused_not_clamped(burn, laps):
    """Rule 9: a non-positive burn is not a burn of zero, and a figure with no
    laps behind it is not a measurement (rule 4). Neither becomes the bar."""
    targets = PlanTargets.from_plan(PLAN)
    targets.install_measured_burn(burn, laps=laps, basis="the race")
    assert targets.measured_burn_l is None
    assert targets.for_lap(compound="RS", saving=False, lap_on_set=1,
                           fuel_at_start_l=90.0).burn_l == PLANNED_BURN


# ------------------------------- rule 4: which population is behind the burn

def test_the_higher_of_two_basis_says_which_of_the_two_won():
    """Laps 13-15 and 25-26 of this race walked the installed burn's lap count
    9 -> 2 -> 3 and 19 -> 3 while the figure moved 1.14% and 0.97% - about
    0.4 sigma of one lap's measured scatter (sd 0.214 L/lap, 22 green laps).
    One name covered both outcomes, so a claim off two laps and a claim off
    nineteen were recorded identically."""
    from pitcrew.race.expectations import (FUEL_BASIS_HIGHER_RACE,
                                           FUEL_BASIS_HIGHER_STINT)

    race = a_race()
    drive(race, 24)
    burn, laps, basis = race.expect.current_fuel_basis()
    assert basis in (FUEL_BASIS_HIGHER_RACE, FUEL_BASIS_HIGHER_STINT)
    # Whichever won, the laps reported are that population's.
    if basis == FUEL_BASIS_HIGHER_RACE:
        assert laps == race.expect.race_burn_laps()
        assert burn == race.expect.race_fuel_per_lap_l()
    else:
        assert laps == race.expect.stint_green_laps()
        assert burn > race.expect.race_fuel_per_lap_l()


def test_a_hedged_basis_is_hedged_from_one_list():
    """A basis split in two must not quietly stop hedging at one consumer."""
    from pitcrew.race.expectations import (FUEL_BASES_HEDGED,
                                           FUEL_BASIS_HIGHER_RACE,
                                           FUEL_BASIS_HIGHER_STINT,
                                           FUEL_BASIS_STINT)

    assert FUEL_BASIS_HIGHER_RACE in FUEL_BASES_HEDGED
    assert FUEL_BASIS_HIGHER_STINT in FUEL_BASES_HEDGED
    assert FUEL_BASIS_STINT not in FUEL_BASES_HEDGED


def test_a_two_lap_stint_figure_carries_no_reference_load():
    """The load anchors the burn to the tank it was measured at. Two laps have
    no load worth anchoring to - and that is now read off the basis rather
    than asked a second time by comparing values (rule 12)."""
    from pitcrew.race.expectations import FUEL_BASIS_HIGHER_STINT

    race = a_race()
    drive(race, 14)
    if race.expect.current_fuel_basis()[2] == FUEL_BASIS_HIGHER_STINT:
        assert race.expect.current_fuel_reference_load_l() is None


def test_a_re_arm_puts_the_target_back_on_the_plan():
    """Rule 11: state that outlives a session is read as if it belongs to
    this one. `PlanTargets` is built in `__init__`, so a re-arm on the same
    coordinator would open the next attempt judging its laps against the burn
    the LAST one measured - the practice-burn-in-a-race failure with the
    sides swapped. And the reset needs a caller, which is the half rule 11
    says is usually missing."""
    race = a_race()
    drive(race, 10)
    assert race.targets.measured_burn_l is not None

    assert race.arm(None, PlanContext(
        car="Ford Shelby GT350R '16", track="Mount Panorama Circuit",
        layout="Full Course", race_laps=28)) is True
    assert race.targets.measured_burn_l is None
    fresh = race.targets.for_lap(compound="RS", saving=False, lap_on_set=1,
                                 fuel_at_start_l=100.0)
    assert fresh.burn_source == BURN_BASIS_PLAN
    assert fresh.burn_l == pytest.approx(PLANNED_BURN)
