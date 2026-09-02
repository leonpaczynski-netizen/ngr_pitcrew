"""When comparing compounds cannot change the plan, and saying so.

At this driver's 2x wear both reasons hold at once, so the search that ranks
compound sequences is settling a question the fuel load already answered - and
until now it printed a confident comparison of two options that were never
really two.
"""
from __future__ import annotations

from pitcrew.strategy.model import (
    COMPOUND_GAP_FLOOR_S,
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
