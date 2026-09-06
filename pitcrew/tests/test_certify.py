"""The gate between a plan somebody wrote and a car that has to drive it."""
from __future__ import annotations

from pitcrew.strategy.certify import certify
from pitcrew.strategy.model import RaceInputs


def inputs(**over) -> RaceInputs:
    base = dict(race_laps=20, lap_time_ms=110_000, fuel_capacity_l=100.0,
                fuel_per_lap_l=6.0, wear_per_lap=0.05,
                available_compounds=("RH", "RM"), required_compounds=())
    base.update(over)
    return RaceInputs(**base)


def plan(*stints, stops=None) -> dict:
    out = {"stints": list(stints)}
    if stops is not None:
        out["stops"] = stops
    return out


def stint(laps, compound="RH", fuel=60.0) -> dict:
    return {"laps": laps, "compound": compound, "fuel_l": fuel}


def test_a_driveable_plan_is_certified():
    got = certify(plan(stint(10), stint(10, "RM")), inputs())
    assert got.certified
    assert "Driveable" in got.describe()


def test_the_audits_own_failure_is_refused():
    """12 Aug 2026: the app ranked the most impossible plan cheapest and asked
    for **"Fuel to 510 litres"** into a hundred-litre tank. That is the whole
    argument for this module - a plan can be internally consistent, well
    argued and undriveable."""
    got = certify(plan(stint(10, fuel=510.0), stint(10, "RM")), inputs())
    assert not got.certified
    assert any("510" in r and "100" in r for r in got.refusals)


def test_a_stint_past_the_tyres_life_is_refused():
    """`0.85 / w` stops the stint before the cliff, and the cliff's onset is
    sharp enough that overshooting costs far more than undershooting."""
    got = certify(plan(stint(30), stint(10, "RM")), inputs())
    assert not got.certified
    assert any("tyre good for" in r for r in got.refusals)


def test_a_stint_the_tank_cannot_reach_is_refused():
    got = certify(plan(stint(19, fuel=99.0), stint(1, "RM", fuel=6.0)),
                  inputs(wear_per_lap=None))
    assert not got.certified
    assert any("tank that reaches" in r for r in got.refusals)


def test_a_plan_that_never_reaches_the_flag_is_refused():
    got = certify(plan(stint(8), stint(8, "RM")), inputs())
    assert not got.certified
    assert any("never reach the flag" in r for r in got.refusals)


def test_a_compound_the_event_does_not_offer_is_refused():
    got = certify(plan(stint(10), stint(10, "RS")), inputs())
    assert not got.certified
    assert any("not available" in r for r in got.refusals)


def test_a_required_compound_the_plan_skips_is_refused():
    got = certify(plan(stint(20)), inputs(required_compounds=("RM",)))
    assert not got.certified
    assert any("the rules require" in r for r in got.refusals)


def test_a_stop_count_that_contradicts_the_stints_is_refused():
    got = certify(plan(stint(10), stint(10, "RM"), stops=2), inputs())
    assert not got.certified
    assert any("stop but has" in r or "stops but has" in r
               for r in got.refusals)


def test_an_unmeasured_compound_warns_and_does_not_refuse():
    """It can be driven. What cannot be trusted is the time it was costed at -
    `CLAUDE.md` §4.5, nothing derived presented as measured."""
    got = certify(plan(stint(10), stint(10, "RM")), inputs())
    assert got.certified
    assert any("no measured profile" in w for w in got.warnings)


def test_what_could_not_be_checked_is_named_rather_than_passed():
    """**Silence is never a pass.** A plan certified by a gate that skipped
    half its tests carries the authority without the arithmetic."""
    got = certify(plan(stint(10), stint(10, "RM")),
                  inputs(fuel_capacity_l=None, wear_per_lap=None))
    assert got.certified
    assert any("tank's capacity" in u for u in got.unchecked)
    assert any("no wear rate" in u for u in got.unchecked)
    assert "Not checked" in got.describe()


def test_a_timed_race_has_its_lap_count_checked_against_the_clock():
    """A timed race's distance is an OUTPUT of the plan - so it is computed
    FROM the plan: its stops, its fills at the pump's rate, the lane loss and
    the dead time come off the clock, and the stints are judged against what
    is left. It used to be listed as unchecked by design, and the one plan
    that was a lap long (Deep Forest, 6 Sep 2026) armed on that."""
    got = certify(plan(stint(10), stint(10, "RM")),
                  inputs(race_laps=None, race_minutes=50.0))
    assert not any("reach the flag" in r for r in got.refusals)
    assert not any("lap count" in u for u in got.unchecked)
    # A plan that outruns the clock is refused, and the refusal says by
    # how much and with how many stops.
    long = certify(plan(stint(30), stint(30, "RM")),
                   inputs(race_laps=None, race_minutes=50.0))
    assert any("clock allows about" in r for r in long.refusals)


def test_an_empty_or_nonsense_plan_is_refused_outright():
    assert not certify({}, inputs()).certified
    assert not certify(plan({"laps": 0}), inputs()).certified
    assert not certify(plan({"laps": "ten"}), inputs()).certified


def test_an_electric_cars_zero_tank_is_not_treated_as_an_error():
    """A capacity of 0 is a real value for an EV, not a missing one."""
    got = certify(plan(stint(10, fuel=None), stint(10, "RM", fuel=None)),
                  inputs(fuel_capacity_l=0.0))
    assert any("no fuel tank" in u for u in got.unchecked)
