"""Does a harder compound ever win, and does the model know why?

The question the driver actually asks before a race: is it worth running the
harder tyre longer to skip a stop? Answering it needs three things the model
did not have — a pace delta per compound, a wear rate per compound, and a
search that considers *which* compound runs *when* rather than assuming they
are all the reference.

The comparison is on **total race time**, because that is the only comparison
that decides anything. A pace deficit is paid every lap; a pit stop is paid
once.
"""
from __future__ import annotations

from pitcrew.analysis.session import LapInput
from pitcrew.strategy.evidence import compound_profiles
from pitcrew.strategy.model import (
    SOURCE_ASSUMED,
    SOURCE_DECLARED,
    SOURCE_MEASURED,
    CompoundProfile,
    RaceInputs,
    allocate_laps,
    build_plan,
    recommend,
)


def a_race(*, laps: int = 30, rh_wear: float = 0.026,
           rh_delta: float = 0.60, rs_wear: float = 0.055,
           **overrides) -> RaceInputs:
    """A 30-lap race with a soft and a hard, both measured.

    The soft is quicker and wears roughly twice as fast; the hard's rate is
    set so it can just go the distance. That is the shape where the crossover
    question has a real answer either way.
    """
    fields = dict(
        race_laps=laps, lap_time_ms=93_000, fuel_per_lap_l=2.6,
        fuel_capacity_l=100.0, refuel_rate_lps=2.5, pit_loss_s=20.0,
        available_compounds=("RS", "RH"), evidence_compound="RS",
        wear_per_lap=rs_wear,
        compound_profiles={
            # `pace_known` spelled out: these two are declared measured and
            # carry a real delta, and the export now emits null for a gap
            # nothing has established. A fixture that leaves it False is
            # describing a comparison that was never made.
            "RS": CompoundProfile("RS", 0.0, rs_wear, SOURCE_MEASURED, 12, 1,
                                  pace_known=True),
            "RH": CompoundProfile("RH", rh_delta, rh_wear, SOURCE_MEASURED, 11,
                                  1, pace_known=True),
        })
    fields.update(overrides)
    return RaceInputs(**fields)


def winner(inputs: RaceInputs):
    return recommend(inputs)[0]


# ------------------------------------------------------- the crossover itself

def test_a_slower_compound_wins_when_it_deletes_a_stop():
    """0.6 s/lap over 30 laps is 18 s. A stop costs more than that."""
    best = winner(a_race(rh_delta=0.60))
    assert best.stops == 0
    assert best.compounds == ("RH",)


def test_the_stop_comes_back_when_the_harder_tyre_costs_too_much():
    """Same tyre life, but now the pace deficit outweighs the stop."""
    best = winner(a_race(rh_delta=1.60))
    assert best.stops == 1
    assert set(best.compounds) == {"RS"}


def test_the_crossover_is_reported_not_just_acted_on():
    best = winner(a_race(rh_delta=0.60))
    crossover = best.crossover
    assert crossover is not None
    assert crossover["winner"]["compounds"] == ["RH"]
    assert crossover["stopsSaved"] == 1
    assert crossover["alternative"]["lostBySeconds"] > 0
    assert crossover["source"] == "derived-from-total-race-time"


def test_the_break_even_says_how_close_the_call_was():
    """A tenth either way is the difference between two race plans.

    **The fixture delta moved from 1.60 to 1.25 on 2 Sep 2026, and the reason
    is the point of the test.** A stop stopped costing 7.5 s it never cost -
    `pit_loss_source` is `declared` on every event, a declared pit loss is
    already the whole non-fuel cost, and the model was adding a dead time on
    top of it. A cheaper stop makes the extra-stop strategy better, so the
    break-even moved from about 1.45 to 1.213 s/lap. That is a quarter of a
    second of compound delta, which is exactly the "tenth either way" this
    test exists to protect.
    """
    close = winner(a_race(rh_delta=1.25)).crossover
    assert close["alternativePaceDeltaSPerLap"] == 1.25
    # The hard loses, but only just: it would draw a little under its actual
    # deficit. That is a call worth re-measuring rather than settling.
    assert 1.1 < close["breakEvenSPerLap"] < 1.25


def test_a_harder_tyre_that_cannot_go_the_distance_is_not_offered():
    """No stint may exceed 0.85/w, however attractive skipping the stop is."""
    plans = recommend(a_race(rh_wear=0.05, rh_delta=0.10))
    # 0.85/0.05 is 17 laps, well short of 30, so no no-stop plan survives.
    assert all(plan.stops >= 1 for plan in plans)


def test_compounds_are_searched_in_order_not_just_as_a_set():
    """Which tyre runs when matters - stint length follows the tyre on it."""
    plans = recommend(a_race())
    sequences = {plan.compounds for plan in plans}
    assert ("RS", "RH") in sequences
    assert ("RH", "RS") in sequences


def test_the_split_between_two_compounds_is_optimised_not_shared():
    """An even split is not a strategy, it is an average.

    Which way the laps fall depends on the pace gap, not on which tyre lasts
    longer: here the soft is 0.6 s/lap quicker, so the answer is to run it to
    its own limit and give the hard what is left. The old code filled each
    stint to its cap in turn and called that a plan.
    """
    from pitcrew.strategy.model import elapsed_for_s, stint_limit

    inputs = a_race()
    plan = build_plan(inputs, stops=1, compounds=["RS", "RH"])
    soft, hard = plan.stints
    assert soft.laps + hard.laps == inputs.race_laps

    profiles = [inputs.profile_for("RS"), inputs.profile_for("RH")]
    chosen = elapsed_for_s(inputs, [soft.laps, hard.laps], profiles)
    even = inputs.race_laps // 2
    caps = [stint_limit(inputs, p)[0] for p in profiles]
    if all(cap is None or even <= cap for cap in caps):
        assert chosen <= elapsed_for_s(inputs, [even, inputs.race_laps - even],
                                       profiles)


def test_allocation_still_returns_the_full_race_when_nothing_fits():
    """The shortfall has to stay visible as a number, not be rounded away."""
    laps = allocate_laps(40, [10, 10])
    assert sum(laps) == 40


def test_an_unknown_limit_falls_back_to_an_even_split():
    assert allocate_laps(30, [None, None]) == [15, 15]


# ------------------------------------------------------------- honest sources

def test_an_unmeasured_compound_is_planned_but_never_called_measured():
    """It inherits the reference rate, and the plan says so."""
    inputs = RaceInputs(
        race_laps=20, lap_time_ms=93_000, fuel_per_lap_l=2.6,
        fuel_capacity_l=100.0, wear_per_lap=0.04,
        available_compounds=("RM", "RH"), evidence_compound="RM",
        compound_profiles={
            "RM": CompoundProfile("RM", 0.0, 0.04, SOURCE_MEASURED, 12, 1)})
    plan = build_plan(inputs, stops=1, compounds=["RM", "RH"])
    assert inputs.profile_for("RH").source == SOURCE_ASSUMED
    assert inputs.profile_for("RH").wear_per_lap == 0.04
    assert plan.rests_on_assumption
    assert any("no measured rate of its own" in note for note in plan.notes)


def test_an_untested_compound_creates_no_plan_and_no_phantom_crossover():
    """With only RS measured, RH used to be planned on RS's inherited rate,
    tie to the second, and the crossover had to caption a dead heat as "not
    a comparison yet". Yas Marina, 16 Aug 2026, showed where that road ends:
    the night-race plan suggested compounds nobody had ever run. The
    untested tyre is no longer planned at all - so there is nothing to
    compare, and no untested stint to suggest."""
    inputs = RaceInputs(
        race_laps=30, lap_time_ms=93_000, fuel_per_lap_l=2.6,
        fuel_capacity_l=100.0, wear_per_lap=0.026,
        available_compounds=("RS", "RH"), evidence_compound="RS",
        compound_profiles={
            "RS": CompoundProfile("RS", 0.0, 0.026, SOURCE_MEASURED, 12, 1)})
    plans = recommend(inputs)
    assert all(stint.compound == "RS"
               for plan in plans for stint in plan.stints)
    assert plans[0].crossover is None, (
        "one tested compound leaves nothing to cross over")


def test_a_decided_call_says_by_how_much_it_was_decided():
    verdict = winner(a_race(rh_delta=0.60)).crossover["verdict"]
    assert "RH beats RS/RS" in verdict
    assert "saving 1 stop" in verdict


def test_a_close_call_says_it_is_close():
    """A tenth either way decides the race, and he should know that.

    Delta moved with the break-even - see
    `test_the_break_even_says_how_close_the_call_was`.
    """
    verdict = winner(a_race(rh_delta=1.25)).crossover["verdict"]
    assert "It is close" in verdict
    assert "Re-measure before committing" in verdict


def test_the_export_carries_a_real_compound_delta_not_a_placeholder():
    inputs = a_race(rh_delta=0.60)
    best = winner(inputs)
    exported = best.as_export(inputs)
    assert exported["assumptions"]["compoundDeltaSPerLap"] == 0.6
    assert exported["compoundCrossover"]["stopsSaved"] == 1
    assert {p["compound"] for p in exported["compoundProfiles"]} == {"RH"}


# ------------------------------------------- measuring profiles from practice

def stint_laps(compound: str, count: int, *, lap_ms: int,
               start: int, worst: float | None) -> list[LapInput]:
    laps = []
    for offset in range(count):
        num = start + offset
        final = offset == count - 1
        # The tank descends across the run. A fixture that refills every lap
        # is a fixture of consecutive pit stops, and the run splitter reads it
        # as exactly that.
        laps.append(LapInput(
            lap_num=num, lap_time_ms=lap_ms,
            fuel_start=round(100.0 - 2.6 * offset, 2),
            fuel_end=round(100.0 - 2.6 * (offset + 1), 2),
            compound=compound, is_pit_lap=final,
            wear_fl=worst if final else None))
    return laps


def test_pace_and_wear_are_measured_per_compound_from_practice():
    """Ten laps on each, the gauge read as each set came off."""
    laps = (stint_laps("RS", 10, lap_ms=93_000, start=1, worst=0.55)
            + stint_laps("RH", 10, lap_ms=93_600, start=11, worst=0.30))
    profiles = compound_profiles(laps, "RS")

    assert profiles["RS"].source == SOURCE_MEASURED
    assert profiles["RS"].pace_delta_s == 0.0
    assert profiles["RS"].wear_per_lap == 0.055
    # The hard is six tenths slower and wears at a bit over half the rate.
    assert profiles["RH"].pace_delta_s == 0.6
    assert profiles["RH"].wear_per_lap == 0.03


def test_a_compound_run_without_a_gauge_reading_is_declared_not_measured():
    """Its pace is known; its wear rate - which sets the stint - is not."""
    laps = (stint_laps("RS", 10, lap_ms=93_000, start=1, worst=0.55)
            + stint_laps("RH", 10, lap_ms=93_600, start=11, worst=None))
    profiles = compound_profiles(laps, "RS")
    assert profiles["RH"].source == SOURCE_DECLARED
    assert profiles["RH"].wear_per_lap is None
    assert profiles["RH"].pace_delta_s == 0.6


def test_a_compound_never_run_gets_no_profile_at_all():
    """Rather than one invented from the compound next to it on the list."""
    laps = stint_laps("RS", 10, lap_ms=93_000, start=1, worst=0.55)
    assert set(compound_profiles(laps, "RS")) == {"RS"}


# --------------------------------------------------- the reference compound

def test_the_reference_compound_is_the_most_run_one():
    from pitcrew.strategy.evidence import reference_compound
    laps = (stint_laps("RS", 4, lap_ms=93_000, start=1, worst=0.2)
            + stint_laps("RH", 9, lap_ms=93_600, start=5, worst=0.2))
    assert reference_compound([lap for lap in laps if lap.counted]) == "RH"


def test_an_even_comparison_picks_the_same_reference_every_run():
    """Two equal stints on two compounds is the *normal* shape of a
    comparison, so a tie is the common case, not the edge one.

    This used to iterate a set of strings, so the winner depended on hash
    randomisation - a different reference per process, and with it a flipped
    sign on every pace delta in the table.
    """
    from pitcrew.strategy.evidence import reference_compound
    laps = (stint_laps("RS", 12, lap_ms=93_000, start=1, worst=0.66)
            + stint_laps("RH", 12, lap_ms=93_600, start=13, worst=0.36))
    counted = [lap for lap in laps if lap.counted]
    # The one that ran first, and the same one however the strings hash.
    assert reference_compound(counted) == "RS"
    assert len({reference_compound(counted) for _ in range(50)}) == 1
