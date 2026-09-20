"""The declared fuel map re-costs the plan's burn, or says why it cannot.

Bathurst Rd 8, 20 Sep 2026. The driver chose **fuel map 3** at the last minute
for throttle stability. The plan was costed at 10.625 L/lap off map-1 practice
laps; the race burned 8.2-8.5. Twenty-two percent out on the one number that
decides the stop count, and 10.625 x 0.85 = 9.03 - which over 28 laps needs
253 L and is **two stops, not three**. The right answer would have fallen out
of a table this repo already had: `FUEL_MAP_CONSUMPTION` existed in
`strategy/model.py` and was referenced by nothing but its own tests.

**The app cannot observe the map.** There are zero readers of it in
`pitcrew/telemetry/` because GT7 broadcasts no such channel - the declaration
on the event page is the only route in. So the job is not to predict the
driver's decision, it is to absorb it, and to refuse loudly where it cannot.

The *recommendation* half is deliberately not rebuilt: `race/calls.py`'s
`fuel_map_for` stays deleted, and the refusal card says the door is his to
open. This records the map and costs against it.
"""
from __future__ import annotations

import pytest

from pitcrew.strategy.evidence import _evidence_fuel_map
from pitcrew.strategy.model import FUEL_MAP_CONSUMPTION, burn_at_fuel_map


class _Lap:
    def __init__(self, fuel_map=None):
        self.fuel_map = fuel_map


# ------------------------------------------------------------- the re-cost

def test_map_1_evidence_re_costs_for_a_map_3_race():
    """The Bathurst arithmetic, which nothing in the app could do."""
    burn, note = burn_at_fuel_map(10.625, measured_on=1, racing_on=3)
    assert burn == pytest.approx(10.625 * FUEL_MAP_CONSUMPTION[3], abs=0.001)
    assert burn == pytest.approx(9.031, abs=0.001)
    assert "[ASSUMED]" in note, "rule 5: derived is never presented as measured"
    assert "x0.778" in note, "and the table's own error is on the record"


def test_a_leaner_evidence_map_costs_the_race_richer():
    """The conversion runs both ways - practice on 6, racing on 1."""
    burn, note = burn_at_fuel_map(5.0, measured_on=6, racing_on=1)
    assert burn == pytest.approx(10.0, abs=0.001)
    assert "re-costed for map 1" in note


def test_the_same_map_both_ends_names_it_and_changes_nothing():
    burn, note = burn_at_fuel_map(10.625, measured_on=3, racing_on=3)
    assert burn == 10.625
    assert note == "measured and raced on fuel map 3"


# --------------------------------------------------------------- the refusals

def test_an_unrecorded_practice_map_is_not_assumed_to_be_map_1():
    """`laps.fuel_map` has been NULL on every lap since session 83, so this is
    the usual state of the archive. Rule 3: missing is missing. The burn
    stands unchanged and the plan says out loud that it could not be
    re-costed - silence would read as "the question does not arise"."""
    burn, note = burn_at_fuel_map(10.625, measured_on=None, racing_on=3)
    assert burn == 10.625
    assert "NOT" in note and "re-costed" in note
    assert "declare the map" in note


def test_no_declared_race_map_leaves_everything_alone():
    """Today's behaviour for every event but four in the whole database."""
    assert burn_at_fuel_map(10.625, measured_on=1, racing_on=None) == (
        10.625, None)


@pytest.mark.parametrize("racing_on", [0, 7, -1])
def test_a_map_outside_one_to_six_is_refused(racing_on):
    burn, note = burn_at_fuel_map(10.625, measured_on=1, racing_on=racing_on)
    assert burn == 10.625
    assert "not one of 1-6" in note


def test_no_burn_at_all_stays_no_burn():
    assert burn_at_fuel_map(None, measured_on=1, racing_on=3) == (None, None)


# -------------------------------------------------- which map the laps were on

def test_laps_that_agree_on_one_map_report_it():
    assert _evidence_fuel_map([_Lap(1), _Lap(1), _Lap(1)]) == 1


def test_laps_that_disagree_report_nothing_rather_than_an_average():
    """Two maps across the evidence is two populations 15-50% apart in burn,
    and one figure over both belongs to neither - the same argument as the
    beep's two columns."""
    assert _evidence_fuel_map([_Lap(1), _Lap(3), _Lap(1)]) is None


def test_laps_that_record_nothing_report_nothing():
    assert _evidence_fuel_map([_Lap(), _Lap()]) is None
    assert _evidence_fuel_map([]) is None


def test_one_lap_declaring_a_map_speaks_for_the_set():
    """A partial declaration is still a declaration - the map is a property of
    how the round is being driven, not of the lap."""
    assert _evidence_fuel_map([_Lap(), _Lap(3), _Lap()]) == 3
