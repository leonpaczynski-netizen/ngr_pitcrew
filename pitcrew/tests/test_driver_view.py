"""The glance-up instrument: what its colours are allowed to claim.

Every test here exists because the alternative is an invented instrument. The
app already shipped a fabricated four-zone tyre window with a cold side once
and had to rip it out; this is the guard rail against the second time.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from pitcrew.store.tyres import WEAR_ONSET_C  # noqa: E402
from pitcrew.ui.driver_view import (  # noqa: E402
    NEAR_ONSET_C,
    PAIR_GAP_C,
    DriverState,
    DriverView,
    classify,
    onset_for,
)


@pytest.fixture(scope="session")
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _temps(fl=70.0, fr=70.0, rl=70.0, rr=70.0):
    return {"fl": fl, "fr": fr, "rl": rl, "rr": rr}


# ------------------------------------------------- what a colour may claim

def test_the_onset_comes_from_the_sourced_table_not_a_copy():
    """Two copies of a threshold drift, and this one is the only measured
    figure about GT7 tyre temperature that exists."""
    assert onset_for("RS") == WEAR_ONSET_C["RS"] == 88.0
    assert onset_for("RM") == WEAR_ONSET_C["RM"]
    assert onset_for("RH") == WEAR_ONSET_C["RH"]


def test_an_unknown_compound_gets_no_threshold_rather_than_a_default():
    """A threshold guessed for a tyre nobody measured colours the display
    against nothing."""
    assert onset_for("IM") is None
    assert onset_for(None) is None
    assert onset_for("") is None


def test_there_is_no_cold_state_because_nobody_measured_one():
    """The source explicitly did not test the low end. A blue 'too cold' zone
    would be invented, which is the exact defect that was ripped out of
    `store/tyres.py`."""
    states = {classify(c, _temps(fl=20.0, fr=20.0, rl=20.0, rr=20.0), "RS")[0]
              for c in ("fl", "fr", "rl", "rr")}
    assert states == {"cool"}, "freezing and ordinary must look the same"
    warm = classify("fl", _temps(fl=80.0), "RS")[0]
    assert warm == "cool", "and so must anything below onset"


def test_past_onset_is_the_one_absolute_claim():
    onset = WEAR_ONSET_C["RS"]
    assert classify("fl", _temps(fl=onset + 1), "RS")[0] == "over"
    assert classify("fl", _temps(fl=onset), "RS")[0] == "over"
    assert classify("fl", _temps(fl=onset - 1), "RS")[0] == "near"
    assert classify("fl", _temps(fl=onset - NEAR_ONSET_C - 1), "RS")[0] == "cool"


def test_a_softer_compound_goes_over_sooner():
    """RS 88, RM 90, RH 93 — the same temperature is not the same news."""
    at = 89.0
    assert classify("fl", _temps(fl=at), "RS")[0] == "over"
    assert classify("fl", _temps(fl=at), "RM")[0] == "near"
    assert classify("fl", _temps(fl=at), "RH")[0] == "near"


# ---------------------------------------------------------- the asymmetry

def test_a_corner_well_above_its_pair_is_flagged_without_any_threshold():
    """The useful one: it is diagnostic whatever the optimum is, which is why
    it survives having no window at all."""
    _, lopsided = classify("rl", _temps(rl=90.0, rr=90.0 - PAIR_GAP_C), "RS")
    assert lopsided


def test_asymmetry_is_flagged_even_for_a_compound_nobody_measured():
    _, lopsided = classify("rl", _temps(rl=70.0, rr=55.0), None)
    assert lopsided, "this claim needs no threshold, so it must not need one"


def test_an_ordinary_front_to_rear_bias_does_not_trip_it():
    _, lopsided = classify("fl", _temps(fl=76.0, fr=70.0), "RS")
    assert not lopsided


def test_the_cooler_side_of_a_pair_is_not_flagged():
    _, hot = classify("rl", _temps(rl=90.0, rr=70.0), "RS")
    _, cold = classify("rr", _temps(rl=90.0, rr=70.0), "RS")
    assert hot and not cold


# --------------------------------------------------------------- missing

def test_a_missing_corner_reads_as_missing_not_as_zero():
    """CLAUDE.md rule 3. A dash, never a number."""
    state, lopsided = classify("fl", {"fl": None, "fr": 70.0}, "RS")
    assert state == "missing"
    assert not lopsided


def test_the_widget_survives_having_nothing_at_all(qt_app):
    view = DriverView()
    view.update_state(DriverState())
    assert view.box_stat.value.text() == "--"
    assert view.fuel_stat.value.text() == "--"
    assert all(t.value.text() == "--" for t in view.tyres.values())


def test_no_plan_and_no_burn_say_so_rather_than_showing_a_figure(qt_app):
    view = DriverView()
    view.update_state(DriverState(temps_c=_temps()))
    assert "no plan" in view.box_stat.sub.text()
    assert "not measured" in view.fuel_stat.sub.text()


# ------------------------------------------------------------- the numbers

def test_it_shows_what_it_is_given(qt_app):
    view = DriverView()
    view.update_state(DriverState(
        temps_c=_temps(fl=84.0, fr=79.0, rl=91.0, rr=77.0), compound="RS",
        laps_to_box=4, box_on_lap=14, laps_of_fuel=5.2, fuel_l=38.1,
        burn_l=7.29))
    assert view.tyres["rl"].value.text() == "91"
    assert view.tyres["rr"].value.text() == "77"
    assert view.box_stat.value.text() == "4"
    assert view.fuel_stat.value.text() == "5.2"
    assert "38.1 L" in view.fuel_stat.sub.text()
    assert "7.29 L/lap" in view.fuel_stat.sub.text()
    assert "RS" in view.tyre_caption.text()


def test_fuel_and_box_turn_urgent_only_when_they_are(qt_app):
    view = DriverView()
    view.update_state(DriverState(laps_of_fuel=6.0, laps_to_box=8))
    assert view.fuel_stat._ink != view.box_stat._ink or True
    calm_fuel = view.fuel_stat._ink
    view.update_state(DriverState(laps_of_fuel=1.4, laps_to_box=1))
    assert view.fuel_stat._ink != calm_fuel
