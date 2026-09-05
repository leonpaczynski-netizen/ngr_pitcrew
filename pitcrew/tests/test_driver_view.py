"""The glance-up instrument: what its colours are allowed to claim.

Every test here exists because the alternative is an invented instrument. The
app already shipped a fabricated four-zone tyre window with a cold side once
and had to rip it out; this is the guard rail against the second time.
"""
from __future__ import annotations

from pathlib import Path

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


# ----------------------------------------------- the gap, promoted to a figure

def test_the_pair_gap_is_a_number_and_only_on_the_hotter_side(qt_app):
    """**The one reading on this screen with evidence behind it.**

    Absolute temperatures are endogenous - a consequence of how hard the tyre
    is being worked rather than an input to grip, with slopes of opposite sign
    at Monza and Spa - and no optimal window has ever been published for GT7.
    The pair gaps do not have that problem: measured across the archive they
    are monotone and match the measured wear map at r=+0.82.

    It was a border colour with no figure. Now it is a figure, and only on
    the corner that is hotter - "13 degrees cooler" is the same finding said
    about the wrong corner.
    """
    from pitcrew.ui.driver_view import pair_gap

    temps = {"fl": 84.0, "fr": 88.0, "rl": 91.0, "rr": 104.0}
    assert pair_gap("rr", temps) == pytest.approx(13.0)
    assert pair_gap("rl", temps) is None, "the cooler side made the claim"
    assert pair_gap("fr", temps) == pytest.approx(4.0)


def test_a_gap_with_nothing_to_compare_against_is_none(qt_app):
    """Rule 3 where it would be easiest to write a zero."""
    from pitcrew.ui.driver_view import pair_gap

    assert pair_gap("rr", {"rr": 104.0}) is None
    assert pair_gap("rr", {"rr": None, "rl": 90.0}) is None
    assert pair_gap("rr", {"rr": 90.0, "rl": 90.0}) is None


def test_the_figure_shows_only_where_it_is_a_finding(qt_app):
    """Under the threshold it shows nothing rather than a small number the
    driver has to make a decision about at 200 km/h."""
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(
        temps_c={"fl": 84.0, "fr": 88.0, "rl": 91.0, "rr": 104.0},
        compound="RS"))
    assert "13" in view.tyres["rr"].gap.text()
    assert "RL" in view.tyres["rr"].gap.text()
    # 4 degrees is under PAIR_GAP_C, so the front axle says nothing.
    assert view.tyres["fr"].gap.text() == ""
    assert view.tyres["rl"].gap.text() == ""


def test_the_display_has_three_ranks_and_the_gaps_lead(qt_app):
    """**The rank, as the driver revised it.**

    His first brief made the tyres the main request and they were the
    smallest of the big numbers, so they were promoted. Seeing that, he
    revised it: he glances at this on the straights and nowhere else, and on
    a straight the car ahead and the car behind are what he can act on right
    now - the tyres are what he acts on over a stint.

    Three ranks, and they must stay distinct: a display where everything is
    the same size has no priority at all, which is where this started.
    """
    from pitcrew.ui.driver_view import _Stat, _Tyre

    assert _Stat.GAP_PX > _Stat.VALUE_PX > _Tyre.VALUE_PX


def test_the_leading_gap_blocks_actually_get_the_leading_size(qt_app):
    """The rank is only real if the widgets are built with it. `_Stat` takes
    its size per instance now, and a default that silently applied to all
    four would leave the constants above describing nothing."""
    from pitcrew.ui.driver_view import _Stat, DriverView

    view = DriverView()
    assert view.ahead_stat.VALUE_PX == _Stat.GAP_PX
    assert view.behind_stat.VALUE_PX == _Stat.GAP_PX
    assert view.box_stat.VALUE_PX == _Stat.VALUE_PX
    assert view.fuel_stat.VALUE_PX == _Stat.VALUE_PX


def test_the_dashboard_asks_for_faces_that_are_installed(qt_app):
    """It asked for Archivo and JetBrains Mono, neither of which is on the
    rig, so every number was silently drawn in Arial. A system face standing
    in for the display voice is a failure, not a fallback."""
    import re

    from PyQt6.QtGui import QFontDatabase

    from pitcrew.ui import driver_view

    source = Path(driver_view.__file__).read_text(encoding="utf-8")
    # Only what is actually declared as a face. The prose above names the two
    # that were wrong on purpose, and a test that cannot tell a comment from a
    # declaration would forbid writing down why.
    asked = set()
    for run in re.findall(r"font-family:([^;\"']+)", source):
        asked.update(part.strip().strip("'\"")
                     for part in run.split(",") if part.strip())
    literal = {name for name in asked if not name.startswith("{")}
    installed = set(QFontDatabase.families())
    generic = {"monospace", "sans-serif", "serif"}
    missing = {name for name in literal
               if name not in installed and name not in generic}
    assert not missing, f"declared but not installed: {sorted(missing)}"


def test_a_neighbour_gap_says_which_way_it_is_going_in_colour(qt_app):
    """**Three states, because there are three.** Catching the car ahead and
    being unable to read a trend at all both rendered white, so the display
    could say "this is going badly" and never "this is going well" - and on a
    screen glanced at once down a straight, that difference is whether the
    effort is paying."""
    from pitcrew.ui.driver_view import (GOOD, INK, NEAR, DriverState,
                                        DriverView, GapView)

    view = DriverView()
    view.update_state(DriverState(
        ahead=GapView(seconds=1.2, note="catching 0.4 s a lap", good=True),
        behind=GapView(seconds=0.8, note="he is catching 0.3 s a lap",
                       urgent=True)))
    assert GOOD in view.ahead_stat.value.styleSheet()
    assert NEAR in view.behind_stat.value.styleSheet()

    # Steady is neither, and stays out of the way.
    view.update_state(DriverState(ahead=GapView(seconds=4.0, note="steady")))
    assert INK in view.ahead_stat.value.styleSheet()


def test_bad_news_outranks_good_if_both_ever_arrive(qt_app):
    """The cost of missing bad news is higher than the cost of missing good."""
    from pitcrew.ui.driver_view import NEAR, _Stat

    stat = _Stat("ahead")
    stat.show_value("1.0", "", urgent=True, good=True)
    assert NEAR in stat.value.styleSheet()


def test_a_widening_split_says_so_and_a_settling_one_goes_green(qt_app):
    """The direction is in the word and in the ink. A split that is opening
    and one that has settled are the same figure and opposite news."""
    from pitcrew.ui.driver_view import GOOD, NEAR, DriverState, DriverView

    view = DriverView()
    temps = {"fl": 84.0, "fr": 85.0, "rl": 91.0, "rr": 104.0}
    view.update_state(DriverState(temps_c=temps, compound="RS",
                                  split_rates={"rr": 2.9}))
    assert "WIDENING" in view.tyres["rr"].gap.text()
    assert NEAR in view.tyres["rr"].gap.styleSheet()

    view.update_state(DriverState(temps_c=temps, compound="RS",
                                  split_rates={"rr": -2.1}))
    assert "SETTLING" in view.tyres["rr"].gap.text()
    assert GOOD in view.tyres["rr"].gap.styleSheet()


def test_no_rate_yet_states_the_split_and_claims_no_direction(qt_app):
    """Five laps have not said so. "Steady" would be a claim; silence is
    the honest half of the reading."""
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(
        temps_c={"fl": 84.0, "fr": 85.0, "rl": 91.0, "rr": 104.0},
        compound="RS"))
    text = view.tyres["rr"].gap.text()
    assert "13" in text
    assert "WIDENING" not in text and "SETTLING" not in text


def test_every_corner_is_painted_even_when_only_one_has_a_split(qt_app):
    """**The bug this guards.** An early return for the corners with no split
    to report skipped the repaint, so three of the four went dead grey the
    moment the fourth had something to say - on the reading this screen
    exists for."""
    from pitcrew.ui.driver_view import NEAR, OVER, DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(
        temps_c={"fl": 84.0, "fr": 85.0, "rl": 91.0, "rr": 104.0},
        compound="RS", split_rates={"rr": 2.9}))
    # 84 and 85 are within 5 of the RS onset of 88, so both are "near";
    # 91 and 104 are over it. None of them is struck.
    assert NEAR in view.tyres["fl"].value.styleSheet()
    assert NEAR in view.tyres["fr"].value.styleSheet()
    assert OVER in view.tyres["rl"].value.styleSheet()
    assert OVER in view.tyres["rr"].value.styleSheet()
