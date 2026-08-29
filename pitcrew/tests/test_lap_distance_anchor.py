"""Lap distance, anchored to the circuit rather than integrated blind.

`lap_distance_m` is not in the packet. Measured against each circuit's own
length before this landed:

    Monza full     true 5,793   median 5,748   min 203    max 11,187  sd 1,187
    Watkins long   true 5,423   median 5,412   min 5,163  max  8,278  sd   503
    RBR short      true 2,336   median 2,314   min 2,065  max  3,354  sd   216

Two faults needing opposite treatments: a smooth 0.2-0.9% shortfall that is
correctable because the true length is known, and laps at twice or a third of
a lap that no scale factor rescues.
"""
from __future__ import annotations

import pytest

from dataclasses import dataclass, field, replace

from pitcrew.analysis import distance
from pitcrew.analysis.distance import CIRCUIT_TOLERANCE, anchor, integrated_length


@dataclass
class FakeLap:
    lap_num: int = 1
    frames: list = field(default_factory=list)


def a_lap(total: float, n: int = 20, lap_num: int = 1) -> FakeLap:
    """A lap whose distance channel runs evenly from 0 to `total`."""
    return FakeLap(lap_num, [{"lap_distance_m": total * i / (n - 1),
                              "speed_kph": 100.0} for i in range(n)])


TRUE = 5793.0


# --- the smooth bias, which is correctable ---------------------------------

def test_a_lap_that_ran_short_is_scaled_onto_the_circuit():
    """0.8% at Monza, in the same direction on all three circuits on file.

    It accrues in proportion to distance because it comes from integrating a
    speed that is slightly off, so a linear rescale is the model that matches
    the fault rather than one chosen for convenience.
    """
    result = anchor([a_lap(5748.0)], TRUE)

    assert result.ran
    assert not result.refused
    assert integrated_length(result.laps[0]) == pytest.approx(TRUE)


def test_the_scale_is_applied_all_the_way_along_the_lap():
    """A corner window is a distance RANGE. Correcting only the total would
    leave every window inside the lap exactly where it was."""
    result = anchor([a_lap(5748.0)], TRUE)
    frames = result.laps[0].frames

    half = frames[len(frames) // 2]["lap_distance_m"]
    assert half == pytest.approx(TRUE * (len(frames) // 2) / (len(frames) - 1))


def test_a_lap_that_needs_no_correction_comes_back_untouched():
    """Not an optimisation - so a diff between two exports shows only what
    actually moved."""
    lap = a_lap(TRUE)
    assert anchor([lap], TRUE).laps[0] is lap


# --- the broken laps, which no scale factor rescues -------------------------

def test_a_lap_that_swallowed_a_crossing_is_refused():
    """It integrates to roughly two laps. It is not imprecise about its
    corners; it is measuring a different piece of road."""
    result = anchor([a_lap(11187.0)], TRUE)

    assert len(result.refused) == 1
    assert result.refused[0][1] == pytest.approx(11187.0)


def test_a_fragment_is_refused():
    assert len(anchor([a_lap(203.0)], TRUE).refused) == 1


def test_a_refused_lap_carries_a_null_distance_and_keeps_everything_else():
    """**Nulled rather than dropped.** Its fuel, its time and its temperatures
    were all measured properly; only the distance is untrustworthy. Dropping
    the lap would take four good measurements out to remove one bad one."""
    result = anchor([a_lap(11187.0)], TRUE)
    lap = result.laps[0]

    assert integrated_length(lap) is None
    assert all(frame["lap_distance_m"] is None for frame in lap.frames)
    assert all(frame["speed_kph"] == 100.0 for frame in lap.frames)


def test_the_tolerance_sits_between_the_two_faults():
    """The smooth bias is under 1% on every circuit on file and the broken
    laps are out by 40-100%. Nothing observed sits between, which is what
    makes one threshold able to separate them."""
    assert anchor([a_lap(TRUE * (1 - CIRCUIT_TOLERANCE / 2))], TRUE).refused == []
    assert anchor([a_lap(TRUE * (1 + CIRCUIT_TOLERANCE * 2))], TRUE).refused


# --- what it says about itself ----------------------------------------------

def test_an_unknown_circuit_length_does_not_pretend_to_have_anchored():
    """A layout the catalogue has never heard of is a real state, and an
    uncorrected export must not be indistinguishable from a corrected one."""
    lap = a_lap(5748.0)
    result = anchor([lap], None)

    assert result.ran is False
    assert result.laps[0] is lap
    assert result.as_export()["ran"] is False


def test_the_export_names_the_refused_laps_and_the_length():
    result = anchor([a_lap(5748.0, lap_num=1), a_lap(11187.0, lap_num=2)], TRUE)
    said = result.as_export()

    assert said["circuitLengthM"] == TRUE
    assert said["lapsRefused"] == 1
    assert said["refusedLaps"][0]["lap"] == 2


def test_a_lap_with_no_distance_channel_is_kept_and_not_refused():
    """No channel is not a bad channel. It contributes no corner windows
    either way, so refusing it would report an exclusion that changed no
    number."""
    lap = FakeLap(1, [{"speed_kph": 100.0}])
    result = anchor([lap], TRUE)

    assert result.laps == [lap]
    assert not result.refused


# --- against the archive ----------------------------------------------------

@pytest.mark.parametrize("event_id", [1, 3, 8])
def test_every_anchored_lap_measures_the_circuit(event_id):
    """The end state, on real laps: sd 1,187 m becomes sd 0, and the laps that
    cannot get there carry a null rather than a number nobody measured."""
    from pitcrew.export.build import event_lap_inputs
    from pitcrew.store.db import Store

    store = Store()
    try:
        event = store.get_event(event_id)
        length = distance.circuit_length(store, event)
        assert length, "every circuit with laps on file has a catalogue length"
        result = anchor(event_lap_inputs(store, event_id, "practice"), length)
        measured = [integrated_length(lap) for lap in result.laps]
        assert [m for m in measured if m is not None], "no laps survived"
        for got in measured:
            assert got is None or got == pytest.approx(length, abs=0.5)
    finally:
        store.close()
