"""How `w` is taken from the driver's gauge — the app's most consequential number.

GT7 broadcasts no tyre wear channel, so every stint length in the app comes out
of `0.85 / w` and `w` comes out of these two or three readings. The strongest
branch of it — two readings inside one run, the only one that emits
`confidence: "measured"` — had no test at all, and it was wrong: it subtracted
the *worst corner* at one lap from the *worst corner* at another without
checking they were the same tyre.

Each test here is a regression test for a figure that reached the plan carrying
more authority than it had earned.
"""
from __future__ import annotations

from dataclasses import replace

from pitcrew.analysis.session import LapInput
from pitcrew.analysis.wear import (
    CONFIDENCE_ASSUMED,
    CONFIDENCE_MEASURED,
    METHOD_FRESH_AT_RUN_START,
    METHOD_FRESH_DECLARED,
    METHOD_FRESH_OBSERVED,
    METHOD_GAUGE_DELTA,
    headline_wear,
    modelled_stint_laps,
    run_wear,
    wear_export,
    wear_per_lap,
)


def a_lap(lap_num: int, *, compound: str | None = "RM", step: int | None = None,
          tank: float = 100.0, burn: float = 3.4, **overrides) -> LapInput:
    """One lap, with the tank where it would be that far into a run.

    The fuel channel is what splits runs, so a fixture has to descend from a
    full tank and start again at one — a tank that refills itself every lap is
    a fixture of consecutive pit stops.
    """
    step = lap_num - 1 if step is None else step
    fields = dict(lap_num=lap_num, lap_time_ms=109_000,
                  fuel_start=round(tank - burn * step, 2),
                  fuel_end=round(tank - burn * (step + 1), 2),
                  compound=compound)
    fields.update(overrides)
    return LapInput(**fields)


def a_run(first: int, last: int, *, compound: str | None = "RM",
          reads: dict[int, dict] | None = None) -> list[LapInput]:
    """One tank of laps, with a gauge reading on whichever laps `reads` names."""
    reads = reads or {}
    return [a_lap(n, compound=compound, step=n - first, **reads.get(n, {}))
            for n in range(first, last + 1)]


# ------------------------------------------- the delta between two readings

def test_the_delta_is_taken_corner_against_corner():
    """The defect, reproduced.

    Lap 8 reads all four with the front-left worst at 0.30; lap 18 reads only
    the rears, worst 0.45. `max - max` is 0.015 a lap - a 56-lap stint, tagged
    `measured`, on a set the front-left finishes by lap 22. Compared per
    corner the right-rear is doing 0.03 a lap and the answer is 28.
    """
    laps = a_run(1, 20, reads={
        8: dict(wear_fl=0.30, wear_fr=0.26, wear_rl=0.15, wear_rr=0.15),
        18: dict(wear_rl=0.44, wear_rr=0.45)})
    record = run_wear(laps)[0]
    assert record.method == METHOD_GAUGE_DELTA
    assert record.rate == 0.03
    assert modelled_stint_laps(laps) == 28


def test_a_limiting_corner_that_changes_identity_cannot_understate_the_rate():
    """`max(later) - max(earlier) <= max(per-corner delta)` is an identity.

    So the old arithmetic could only ever err toward a longer stint - the
    direction §5.1 says costs most. Here the front-left leads at lap 5 and the
    rear-right has overtaken it by lap 15: worst-against-worst gives
    (0.60-0.40)/10 = 0.02, while the rear-right has actually done 0.05 a lap.
    """
    laps = a_run(1, 16, reads={
        5: dict(wear_fl=0.40, wear_fr=0.30, wear_rl=0.10, wear_rr=0.10),
        15: dict(wear_fl=0.55, wear_fr=0.45, wear_rl=0.55, wear_rr=0.60)})
    assert run_wear(laps)[0].rate == 0.05


def test_readings_sharing_no_corner_fall_through_to_the_single_reading_path():
    """Partial reads are a designed input - the gauge lets him clear a corner
    and the contract says an unread corner stays null. Two readings that name
    no tyre in common are not a delta, and discarding the later one throws
    away a rate that is perfectly usable on its own.
    """
    laps = a_run(1, 12, reads={4: dict(wear_fl=0.2),
                               12: dict(wear_rr=0.6)})
    record = run_wear(laps)[0]
    assert record.method == METHOD_FRESH_AT_RUN_START
    assert record.rate == 0.05
    assert record.confidence == CONFIDENCE_ASSUMED


def test_a_gauge_that_went_backwards_says_so_in_its_own_words():
    """It used to return None and then explain it with "the readings do not
    span any laps" - about two readings ten laps apart."""
    laps = a_run(1, 20, reads={8: dict(wear_rl=0.55, wear_rr=0.55),
                               18: dict(wear_rl=0.42, wear_rr=0.40)})
    record = run_wear(laps)[0]
    assert record.rate is None
    assert "no higher at lap 18 than at lap 8" in record.unavailable_reason
    assert "do not span any laps" not in record.unavailable_reason


# ------------------------------------------------------ what counts as measured

def test_only_two_readings_or_his_word_make_a_rate_measured():
    laps = a_run(1, 12, reads={4: dict(wear_fl=0.2), 12: dict(wear_fl=0.6)})
    assert run_wear(laps)[0].confidence == CONFIDENCE_MEASURED

    declared = a_run(1, 12, reads={12: dict(wear_fl=0.6)})
    declared[0] = replace(declared[0], tyres_fresh=True)
    record = run_wear(declared)[0]
    assert record.method == METHOD_FRESH_DECLARED
    assert record.confidence == CONFIDENCE_MEASURED


def test_a_set_called_fresh_by_its_temperatures_is_assumed_not_measured():
    """`fresh_by_temperature` is the app reading a band the app chose, against
    a `FRESH_TYRE_TEMP_C` that is itself a correction of a fabricated figure.
    Four of six Monza runs carried `confidence: measured` on it, and four runs
    are enough to promote the whole payload to `modelConfidence: measured`.
    Contract §6.1 and §8 make `measured` conditional on two readings or the
    driver's own declaration and on nothing else.
    """
    frames = [{"speed_kph": 0.0, "temp_fl": 68.0, "temp_fr": 68.0,
               "temp_rl": 68.0, "temp_rr": 68.0}]
    laps = a_run(1, 12, reads={12: dict(wear_fl=0.6)})
    laps[0] = replace(laps[0], frames=frames)

    record = run_wear(laps)[0]
    assert record.tyres_fresh is True
    assert record.method == METHOD_FRESH_OBSERVED
    assert record.confidence == CONFIDENCE_ASSUMED
    # And it says what it assumed, which the `measured` tag used to suppress.
    assert record.as_export()["assumesFreshAtLap"] == 1
    assert wear_export(laps)["modelConfidence"] == CONFIDENCE_ASSUMED


# ------------------------------------------------------------ the headline rate

def test_the_headline_rate_names_its_compound_and_its_runs():
    laps = (a_run(1, 10, compound="RM", reads={10: dict(wear_fl=0.4)})
            + a_run(11, 20, compound="RM", reads={20: dict(wear_fl=0.6)}))
    headline = headline_wear(laps)
    assert headline["compound"] == "RM"
    assert headline["runIds"] == [1, 2]
    assert headline["runsMeasured"] == 2
    assert headline["runs"] == 2
    # The mean of the two runs - the same arithmetic `byCompound` uses, so one
    # tyre cannot carry two figures computed two ways inside one payload.
    assert headline["wearPerLap"] == 0.05
    assert wear_export(laps)["byCompound"]["RM"]["wearPerLap"] == 0.05


def test_two_compounds_with_rates_refuse_a_headline_rather_than_pick_one():
    """It was `rates[-1]`, whichever run happened to be last. The Monza export
    carried `modelledStintLaps: 26` off a Racing Hard rate while Racing Soft
    reads four laps: a driver planning 26 who fits softs runs six times past
    the cliff."""
    laps = (a_run(1, 10, compound="RH", reads={10: dict(wear_fl=0.3)})
            + a_run(11, 15, compound="RS", reads={15: dict(wear_fl=0.8)}))
    headline = headline_wear(laps)
    assert headline["wearPerLap"] is None
    assert "RH and RS" in headline["unavailable"]
    assert modelled_stint_laps(laps) is None

    payload = wear_export(laps)
    assert payload["modelledStintLaps"] is None
    assert "byCompound" in payload["modelBasis"]

    # Named, and it answers: 0.85 / 0.16.
    assert modelled_stint_laps(laps, compound="RS") == 5
    named = wear_export(laps, compound="RS")
    assert named["modelledStintCompound"] == "RS"
    assert "RS over run 2" in named["modelBasis"]


def test_untagged_runs_use_the_latest_and_say_which_one():
    """No tag is nothing to name, and the runs are still separate sets. The
    latest is the freshest evidence about the car as it is now."""
    laps = (a_run(1, 10, compound=None, reads={10: dict(wear_fl=0.4)})
            + a_run(11, 20, compound=None, reads={20: dict(wear_fl=0.7)}))
    headline = headline_wear(laps)
    assert headline["compound"] is None
    assert headline["runIds"] == [2]
    assert headline["runsMeasured"] == 2
    assert headline["wearPerLap"] == 0.07
    assert "no compound tag" in wear_export(laps)["modelBasis"]


def test_no_reading_anywhere_refuses_in_a_sentence():
    laps = a_run(1, 6)
    assert wear_per_lap(laps) is None
    assert headline_wear(laps)["unavailable"] == (
        "no run carried a usable gauge reading")


# --------------------------------------------------------- the two corroborators

def test_the_temperature_trend_is_fitted_inside_one_run_and_counted():
    """Ten laps rising exactly 1.0 C a lap were reported as 0.56: the two
    half-mean centroids are half a span apart and it divided by the full span.
    Fitted across the session it also spanned eight runs and three compounds,
    which §6.1 forbids of anything.
    """
    def a_temp_lap(lap_num, front, **overrides):
        return a_lap(lap_num, frames=[
            {"temp_fl": front, "temp_fr": front,
             "temp_rl": front - 5.0, "temp_rr": front - 5.0}], **overrides)

    laps = [a_temp_lap(n, 80.0 + n) for n in range(1, 11)]
    by_temp = wear_export(laps)["byTemp"]
    assert by_temp["trendCPerLap"] == 1.0
    assert by_temp["frontRearAsymmetryC"] == 5.0
    assert by_temp["samples"] == 10


def test_the_end_fraction_belongs_to_the_run_the_slope_was_fitted_on():
    """It was `readings[-1]` - his last reading from anywhere in the session,
    published beside a slope fitted on a different run under
    `source: "lap-time-model"`."""
    laps = ([a_lap(n, lap_time_ms=109_000 + n * 100) for n in range(1, 11)]
            + a_run(11, 13, reads={13: dict(wear_fl=0.95)}))
    by_lap_time = wear_export(laps)["byLapTime"]
    assert by_lap_time["fittedRunId"] == 1
    # Run 2's 95% says nothing about the phase run 1 was fitted in.
    assert by_lap_time["estimatedFractionAtEnd"] is None
    assert by_lap_time["phase"] is None
    assert by_lap_time["estimatedFractionSource"] is None
