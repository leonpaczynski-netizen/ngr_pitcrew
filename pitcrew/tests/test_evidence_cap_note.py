"""Naming the cap is not the same as making it actionable.

`binding_limit` stopped the plan calling an evidence cap "fuel", which is the
correctness fix. It still left the driver to work out on his own what would
change it - and at Fuji the answer was **one practice run**.

The tyre allowed 20.7 laps and the tank 15.4, both longer than the 20-lap race.
The longest RS stint on record was 6. So the optimiser produced four stints and
priced them 50 s worse than the one-stop it could not justify, and **nothing
anywhere told him that a single long run would collapse the plan to one stop.**
He found it out by ignoring two box calls and being right.
"""
from __future__ import annotations

import pytest

from pitcrew.strategy.model import (
    CompoundProfile,
    RaceInputs,
    build_plan,
)


def fuji_inputs(*, longest: int = 6, **over) -> RaceInputs:
    """Event 6 as the app had it when it approved the three-stop plan."""
    fields = dict(
        race_laps=20,
        lap_time_ms=98_874,
        fuel_per_lap_l=6.507,
        fuel_capacity_l=100.0,
        wear_per_lap=0.04115,
        refuel_rate_lps=1.0,
        pit_loss_s=20.0,
        mandatory_stops=1,
        available_compounds=("RS",),
        compound_profiles={
            "RS": CompoundProfile(code="RS", wear_per_lap=0.04115,
                                  longest_stint_laps=longest),
        },
    )
    fields.update(over)
    return RaceInputs(**fields)


def note_text(plan) -> str:
    return " ".join(plan.notes)


# ------------------------------------------------------ the note appears

def test_the_plan_says_what_run_would_lift_the_cap():
    plan = build_plan(fuji_inputs(), stops=3)

    said = note_text(plan)
    assert "Capped by evidence" in said, said
    assert "6 laps" in said, "it has to name the cap it is capped by"
    assert "1-stop" in said, (
        "the whole point is telling him what the run would be worth")


def test_it_names_the_ceiling_behind_the_cap():
    """The tank: 100 L at 6.507 L/lap, less the margin the fill carries, is
    14 laps - and that is what a long run actually unlocks. The tyre allows
    more (0.85 / 0.04115 = 20), so the lower of the two is the honest figure
    to quote him."""
    plan = build_plan(fuji_inputs(), stops=3)

    assert "14" in note_text(plan)


def test_it_names_the_compound_the_evidence_is_about():
    plan = build_plan(fuji_inputs(), stops=3)

    assert "RS" in note_text(plan)


# ------------------------------------------------- and stays quiet otherwise

def test_nothing_is_said_when_the_evidence_is_not_the_cap():
    """A long run already on file: the tank binds, and that is a real
    constraint a practice stint cannot argue with."""
    plan = build_plan(fuji_inputs(longest=40), stops=1)

    assert "Capped by evidence" not in note_text(plan)


def test_nothing_is_said_when_lifting_the_cap_would_change_nothing():
    """A cap that costs no stops is not worth a line on a plan he reads
    before a race - the note has to earn its place among the box calls."""
    # Six laps of evidence, but a race short enough that one stint covers it.
    plan = build_plan(fuji_inputs(race_laps=6), stops=0)

    assert "Capped by evidence" not in note_text(plan)


def test_nothing_is_said_when_the_tyre_is_the_real_ceiling():
    """Wear so high the tyre binds below the evidence: a practice run would
    not help, and telling him to do one would waste a session."""
    inputs = fuji_inputs(
        longest=20,
        wear_per_lap=0.3,
        compound_profiles={
            "RS": CompoundProfile(code="RS", wear_per_lap=0.3,
                                  longest_stint_laps=20)},
    )
    plan = build_plan(inputs, stops=6)

    assert "Capped by evidence" not in note_text(plan)


# ------------------------------------------------------------- the wiring

def test_it_is_the_note_the_driver_actually_sees():
    """`strategy_screen` renders `notes[0]` and nothing else. A cap note
    buried under a remark about fuel margin is a cap note nobody reads."""
    plan = build_plan(fuji_inputs(), stops=3)

    assert plan.notes[0].startswith("**Capped by evidence")


def test_a_feasibility_failure_still_outranks_it():
    """A fill bigger than the tank is the thing he has to know first."""
    inputs = fuji_inputs(longest=30, fuel_capacity_l=20.0)
    plan = build_plan(inputs, stops=0)

    assert plan.notes, "an impossible plan has to say why"
    assert not plan.notes[0].startswith("**Capped by evidence")
    assert plan.feasible is False


def test_the_wear_note_no_longer_implies_wear_set_the_length():
    """It read as corroboration: "longest stint ends in the 'flat' phase at
    25% worn" beside a six-lap stint that 0.85 / w would have run to twenty."""
    plan = build_plan(fuji_inputs(), stops=3)

    said = note_text(plan)
    assert "Wear is not what limits it" in said
    assert "Stint length is 0.85 / w with the margin deliberate" not in said


def test_the_note_reaches_the_export_with_the_plan():
    """It is read on the strategy screen before approval and in the export
    afterwards, so it has to travel on the plan rather than be logged."""
    plan = build_plan(fuji_inputs(), stops=3)

    assert any("Capped by evidence" in note for note in plan.notes)
    assert plan.binding_constraint == "evidence"
