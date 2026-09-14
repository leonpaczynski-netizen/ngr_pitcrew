"""The reported constraint has to be the one that actually bound the plan.

Fuji, 24 Aug 2026, approved strategy 13. `stint_limit()` weighs three ceilings
and the plan is laid out against the lowest of them; `max_stint_laps()` weighs
only two and was what the plan reported. So a plan capped at six-lap stints by
"nobody has run further than six laps on this tyre" described itself as
fuel-limited, and the driver was told the stop count was arithmetic when it was
an admission.

    tyre     0.85 / 0.04115  = 20.7 laps
    tank     100 / 6.507     = 15.4 laps
    evidence longest RS stint =  6 laps   <- bound it
    reported                            "fuel"

He ignored two box calls, ran to the flag and finished P5.
"""
from __future__ import annotations

import pytest

from pitcrew.strategy import model
from pitcrew.strategy.model import (CONSTRAINT_EVIDENCE, CONSTRAINT_FUEL,
                                    CONSTRAINT_TYRE, CONSTRAINT_UNKNOWN)


def a_profile(*, code="RS", wear=0.04115, longest=6):
    return model.CompoundProfile(code=code, wear_per_lap=wear,
                                 longest_stint_laps=longest)


def fuji_inputs(**over):
    """The race as the app had it at 20:16:33 on 24 Aug 2026."""
    fields = dict(race_laps=20, fuel_capacity_l=100.0, fuel_per_lap_l=6.507,
                  wear_per_lap=0.04115)
    fields.update(over)
    return fields


class Inputs(model.RaceInputs):
    """The real inputs, with every compound answering as the one under test.

    It used to be a bare object carrying only the three fields `binding_limit`
    read. The tank limit now asks the same question the plan is fuelled with
    (`tank_limited_laps` -> `planned_fill_l`, rule 12), which reads the margin
    and the load too - so the fixture is the dataclass itself, and a field the
    model starts reading cannot be missing from it."""

    def __init__(self, **fields) -> None:
        fields.setdefault("lap_time_ms", 100_000)
        super().__init__(**fields)

    def profile_for(self, code):
        return a_profile(code=code)


# ------------------------------------------------------- the three ceilings

def test_the_lowest_of_the_three_ceilings_is_the_one_reported():
    inputs = Inputs(**fuji_inputs())

    laps, why = model.binding_limit(inputs, [a_profile()])

    assert why == CONSTRAINT_EVIDENCE, (
        "six laps of evidence bound this plan, not the 15.4 the tank allowed")
    assert laps == 6


def test_it_agrees_with_the_caps_the_plan_is_actually_built_from():
    """The defect was these two disagreeing. They may not, ever."""
    inputs = Inputs(**fuji_inputs())
    profile = a_profile()

    assert model.binding_limit(inputs, [profile]) == \
        model.stint_limit(inputs, profile)


def test_fuel_still_binds_when_it_is_genuinely_the_lowest():
    inputs = Inputs(**fuji_inputs())
    # A compound with a long run behind it: the tank is now the tightest.
    laps, why = model.binding_limit(inputs, [a_profile(longest=40)])

    assert why == CONSTRAINT_FUEL
    assert laps == pytest.approx(15, abs=1)


def test_the_tyre_still_binds_when_it_is_genuinely_the_lowest():
    inputs = Inputs(**fuji_inputs(fuel_capacity_l=500.0))
    laps, why = model.binding_limit(inputs, [a_profile(wear=0.15,
                                                       longest=40)])

    assert why == CONSTRAINT_TYRE
    assert laps == pytest.approx(5, abs=1)


# ------------------------------------------------------- across a sequence

def test_a_plan_is_only_as_free_as_its_tightest_stint():
    """Two compounds, and the reported cap is the smaller of the two."""
    inputs = Inputs(**fuji_inputs())

    laps, why = model.binding_limit(
        inputs, [a_profile(code="RH", longest=40), a_profile(code="RS",
                                                             longest=6)])

    assert (laps, why) == (6, CONSTRAINT_EVIDENCE)


def test_no_profile_knows_anything_falls_back_rather_than_inventing():
    inputs = Inputs(race_laps=20, fuel_capacity_l=None, fuel_per_lap_l=None,
                    wear_per_lap=None)
    bare = model.CompoundProfile(code="RS", wear_per_lap=None,
                                 longest_stint_laps=0)

    laps, why = model.binding_limit(inputs, [bare])

    assert why == CONSTRAINT_UNKNOWN
    assert laps is None


def test_a_longest_stint_of_zero_is_not_a_cap_of_zero():
    """`longest_stint_laps` is 0 before anything has run. That is absent, not
    a ceiling - a plan capped at zero laps is not a plan."""
    inputs = Inputs(**fuji_inputs())

    laps, why = model.binding_limit(inputs, [a_profile(longest=0)])

    assert laps and laps > 0
    assert why in (CONSTRAINT_FUEL, CONSTRAINT_TYRE)


# ------------------------------------------------- what the driver is told

def test_the_export_contract_carries_evidence():
    from pitcrew.export import payload

    assert "evidence" in payload.BINDING_CONSTRAINTS, (
        "a constraint the driver is shown but the export cannot carry is a "
        "finding that stops at the app boundary")


def test_the_race_screen_spells_out_what_evidence_limited_means():
    """On its own it reads like a measurement. It is the opposite of one."""
    from pitcrew.ui import race_screen
    import inspect

    source = inspect.getsource(race_screen)
    assert "nothing has run longer" in source
