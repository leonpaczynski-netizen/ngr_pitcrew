"""Tyres at the stop is a decision the plan states and the car says.

Deep Forest, 6 Sep 2026. Ludo wrote "TYRES: DO NOT TAKE THEM" into
`race_knowledge.notes`, which nothing in the race reads. The box call said
"Box this lap. RS." - the plan's compound for the next stint, which under a
helmet is "fit RS" - and the driver took a set: 3 s in the box plus a 1.4 s
cold out-lap, against an 8 s gap to P2. A decision that lives only in prose is
not one the car can say.

The decision now lives on the plan stint (`tyres: true|false`), reaches
`RaceState.next_tyres` through `_apply_stint`, and is spoken by the box call
and shown by the box panel. Absent stays absent: a stint written before the
field existed says the compound as it always did.
"""
from __future__ import annotations

from pitcrew.race.calls import RaceState, _box_now, _tyre_word
from pitcrew.race.coordinator import RaceCoordinator
from pitcrew.ui.driver_view import DriverState


def at_the_box(**over):
    fields = dict(lap=11, laps_total=20, fuel_l=14.0, fuel_per_lap_l=7.7,
                  fuel_capacity_l=100.0, stint_ends_on_lap=11,
                  next_stint_laps=9, further_stop_planned=False,
                  next_compound="RS", laps_estimate_firm=True)
    fields.update(over)
    return RaceState(**fields)


# ------------------------------------------------------------ the sentence

def test_fuel_only_is_said_as_no_tyres():
    call = _box_now(at_the_box(next_tyres=False))
    assert call is not None
    assert call.call == "Box this lap. No tyres."


def test_a_set_going_on_is_said_as_a_decision():
    call = _box_now(at_the_box(next_tyres=True))
    assert call.call == "Box this lap. RS on."


def test_a_plan_that_did_not_say_keeps_the_old_sentence():
    call = _box_now(at_the_box(next_tyres=None))
    assert call.call == "Box this lap. RS."


def test_the_overdue_call_carries_the_same_word():
    call = _box_now(at_the_box(lap=12, next_tyres=False))
    assert call.call == "Box this lap. No tyres."
    assert "overdue" in call.reason


def test_no_compound_named_but_tyres_yes():
    assert _tyre_word(at_the_box(next_compound=None, next_tyres=True)) == " Tyres on."
    assert _tyre_word(at_the_box(next_compound=None, next_tyres=None)) == ""


# --------------------------------------------------------------- the plan

def _plan(**stint2):
    second = {"laps": 9, "compound": "RS", "fuel_l": 69.4, "start_lap": 12}
    second.update(stint2)
    return {"stops": 1, "pit_laps": [11],
            "stints": [{"laps": 11, "compound": "RS", "fuel_l": 85.4,
                        "start_lap": 1}, second]}


def test_the_stint_decision_reaches_the_state():
    race = RaceCoordinator(_plan(tyres=False))
    assert race.state.next_tyres is False
    assert race.state.next_compound == "RS"


def test_a_stint_that_says_tyres_true_reads_true():
    race = RaceCoordinator(_plan(tyres=True))
    assert race.state.next_tyres is True


def test_a_stint_written_before_the_field_reads_none_not_false():
    """Absent is 'nobody said', never 'fuel only' (CLAUDE.md rule 3)."""
    race = RaceCoordinator(_plan())
    assert race.state.next_tyres is None


def test_the_last_stint_has_no_coming_stop_and_no_decision():
    race = RaceCoordinator(_plan(tyres=False))
    race._apply_stint(1)
    assert race.state.next_tyres is None
    assert race.state.next_compound is None


# -------------------------------------------------------------- the board

class _Stat:
    def __init__(self):
        self.shown = None

    def show_value(self, value, caption=None, **_kw):
        self.shown = (value, caption)


def _panel_shows(state: DriverState):
    from pitcrew.ui.driver_view import _BoxPanel

    panel = _BoxPanel.__new__(_BoxPanel)
    for name in ("release_stat", "fuel_stat", "tyre_stat", "out_stat",
                 "next_stat"):
        setattr(panel, name, _Stat())
    _BoxPanel.show_state(panel, state)
    return panel.tyre_stat.shown


def test_the_box_panel_says_no_tyres_when_the_plan_says_fuel_only():
    shown = _panel_shows(DriverState(compound="RS", tyres_at_stop=False,
                                     has_plan=True, in_box=True))
    assert shown == ("NO TYRES", "plan · fuel only")


def test_the_box_panel_marks_a_new_set_as_the_decision_it_is():
    shown = _panel_shows(DriverState(compound="RS", tyres_at_stop=True,
                                     has_plan=True, in_box=True))
    assert shown == ("RS", "plan · new set")


def test_the_box_panel_keeps_the_old_caption_when_the_plan_did_not_say():
    shown = _panel_shows(DriverState(compound="RS", tyres_at_stop=None,
                                     has_plan=True, in_box=True))
    assert shown == ("RS", "plan")
