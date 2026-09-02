"""When comparing compounds cannot change the plan, and saying so.

At this driver's 2x wear both reasons hold at once, so the search that ranks
compound sequences is settling a question the fuel load already answered - and
until now it printed a confident comparison of two options that were never
really two.
"""
from __future__ import annotations

from pitcrew.strategy.model import (
    COMPOUND_GAP_FLOOR_S,
    compound_choice_is_moot,
    _verdict,
    fuel_limited_laps,
    pace_loss_s,
    tyre_limited_laps,
)


def test_fuel_binds_every_stint_at_this_drivers_numbers():
    """Spa: 100 L at 8 L a lap against a tyre wearing about 0.05 a lap.

    A stop in GT7 is a refuel, so a longer-lasting compound can only delete a
    stop if the TYRE is what ends the stint. Here it never is.
    """
    assert fuel_limited_laps(100.0, 8.0) == 11
    assert tyre_limited_laps(0.05) == 17
    assert fuel_limited_laps(100.0, 8.0) < tyre_limited_laps(0.05)


def test_the_soft_never_wears_into_a_real_compound_gap():
    """`pace_loss_s` is flat to 0.50 and his stints end at 0.44-0.56 worst
    corner, so the soft gives back at most 0.15 s a lap by the flag - less
    than any compound gap worth having."""
    assert pace_loss_s(0.44) == 0.0
    assert pace_loss_s(0.56) < COMPOUND_GAP_FLOOR_S


def test_a_moot_comparison_is_said_instead_of_the_table():
    """A table comparing two options where one cannot win is worse than no
    table, because it reads as a finding."""
    said = _verdict({
        "moot": "The compound comparison cannot decide this: the tank ends "
                "every stint at 11 laps.",
        "winner": {"compounds": ["RS", "RS"]},
        "alternative": {"compounds": ["RM", "RM"], "lostBySeconds": 12.0},
        "stopsSaved": 0,
        "alternativePaceDeltaSPerLap": 0.4,
        "breakEvenSPerLap": 0.1,
    }, assumed=False)
    assert said.startswith("The compound comparison cannot decide this")
    assert "beats" not in said


def test_a_comparison_that_can_bite_still_reads_as_a_comparison():
    said = _verdict({
        "moot": None,
        "winner": {"compounds": ["RS", "RS"]},
        "alternative": {"compounds": ["RM", "RM"], "lostBySeconds": 12.0},
        "stopsSaved": 0,
        "alternativePaceDeltaSPerLap": 0.4,
        "breakEvenSPerLap": 0.1,
    }, assumed=False)
    assert "beats" in said
    assert "cannot decide" not in said


def test_the_moot_sentence_outranks_the_unmeasured_note():
    """Both are reasons not to trust the table, and "this cannot decide it"
    is the stronger of the two: it is true even with perfect measurements."""
    said = _verdict({
        "moot": "The compound comparison cannot decide this: fuel binds.",
        "winner": {"compounds": ["RS", "RS"]},
        "alternative": {"compounds": ["RM", "RM"], "lostBySeconds": 0.2},
        "stopsSaved": 0,
        "alternativePaceDeltaSPerLap": 0.0,
        "breakEvenSPerLap": 0.0,
    }, assumed=True)
    assert "cannot decide" in said
    assert "no wear rate has been measured" not in said


# --- the function itself, which the file is named for ----------------------

def _inputs(**overrides):
    from pitcrew.strategy.model import CompoundProfile, RaceInputs

    fields = dict(
        race_laps=20, lap_time_ms=140_000, fuel_per_lap_l=8.0,
        fuel_capacity_l=100.0, refuel_rate_lps=1.0, pit_loss_s=19.5,
        wear_per_lap=0.05, available_compounds=("RS", "RM"),
        compound_profiles={
            "RS": CompoundProfile(code="RS", wear_per_lap=0.05,
                                  source="measured", pace_delta_s=0.0,
                                  pace_known=True),
            "RM": CompoundProfile(code="RM", wear_per_lap=0.03,
                                  source="measured", pace_delta_s=0.5,
                                  pace_known=True),
        },
    )
    fields.update(overrides)
    return RaceInputs(**fields)


def test_at_his_numbers_the_comparison_genuinely_cannot_decide():
    said = compound_choice_is_moot(_inputs())
    assert said is not None
    assert "cannot decide" in said and "wins by construction" in said


def test_a_compound_with_a_shorter_EVIDENCE_ceiling_makes_the_choice_live():
    """The counterexample the two-ceiling version got wrong.

    RS wears slower on paper but has never been run past six laps; RM has
    fourteen on record. RS gives six-lap stints and RM eleven, so RM deletes
    two stops - about 160 s - and the old version declared the comparison moot
    and told him to fit the soft.
    """
    from pitcrew.strategy.model import CompoundProfile

    said = compound_choice_is_moot(_inputs(compound_profiles={
        "RS": CompoundProfile(code="RS", wear_per_lap=0.05, source="measured",
                              pace_delta_s=0.0, pace_known=True,
                              longest_stint_laps=6),
        "RM": CompoundProfile(code="RM", wear_per_lap=0.03, source="measured",
                              pace_delta_s=0.5, pace_known=True,
                              longest_stint_laps=14),
    }))
    assert said is None or "no compound here can delete a stop" not in said


def test_nothing_is_concluded_from_a_fabricated_wear_rate():
    """`profile_for` hands back the reference compound's rate under another
    compound's name when that one has never been gauge-read, so "every tyre
    lasts longer than the tank" was one measured number duplicated."""
    from pitcrew.strategy.model import CompoundProfile

    assert compound_choice_is_moot(_inputs(compound_profiles={
        "RS": CompoundProfile(code="RS", wear_per_lap=0.05, source="measured",
                              pace_delta_s=0.0, pace_known=True),
        "RM": CompoundProfile(code="RM", wear_per_lap=0.05, source="assumed",
                              pace_delta_s=0.0, pace_known=False),
    })) is None


def test_a_moot_verdict_built_on_an_assumption_keeps_its_provenance():
    """Returning early used to delete the [ASSUMED] tail, so a verdict resting
    on an invented rate read with no provenance at all."""
    said = _verdict({
        "moot": "The compound comparison cannot decide this: fuel binds.",
        "winner": {"compounds": ["RS", "RS"]},
        "alternative": {"compounds": ["RM", "RM"], "lostBySeconds": 0.2},
        "stopsSaved": 0,
        "alternativePaceDeltaSPerLap": 0.0,
        "breakEvenSPerLap": 0.0,
    }, assumed=True)
    assert "cannot decide" in said and "[ASSUMED]" in said


def test_an_unknown_fuel_limit_is_not_a_limit_of_zero():
    """CLAUDE.md rule 3, and `fuel_limited_laps`' own docstring says it."""
    assert compound_choice_is_moot(_inputs(fuel_per_lap_l=None)) is None
