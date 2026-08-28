"""A fuel-bound stop the fuel no longer needs is not a stop.

**Fuji, Round 4 GT3, the race this is on file from.** The approved plan was
fuel-bound, three stops, on a tyre the same plan modelled as good for 20.7
laps of a 20-lap race - so every stop in it existed to put fuel in, and none
of them existed for rubber. The event required one stop and he took it on lap
6, filling to 94.0 L with fourteen laps to run at a measured 6.0 L/lap. Even
at the plan's own pessimistic 6.507 L/lap that reaches the flag with room.

He was then told to box twice more. "Box in 2. Stop 3, on the plan." on lap
13, "Box next lap" on 14, "Box this lap" on 15 and again on 16 - for fuel he
was already carrying. He ignored all four, finished P5, and crossed the line
with 8.3 L aboard. The only call that ever questioned it arrived on lap 17,
as `stay-out`, two laps after the box call it was reconsidering.

The driver, 28 Aug 2026: *"When I pitted it should realise I had enough fuel
to get to the end."*
"""
from __future__ import annotations

from pitcrew.race.calls import (
    BOX_NOW,
    BOX_SOON,
    STOPS_OFF,
    TO_THE_FLAG,
    TO_THE_STOP,
    RaceState,
    fuel_frame,
    fuel_reaches_flag,
    next_call,
    stop_still_needed,
)


def after_the_stop(**overrides) -> RaceState:
    """Lap 8 at Fuji: one stop taken, tank filled, twelve laps to run."""
    fields = dict(lap=8, laps_total=20, fuel_l=82.3, fuel_per_lap_l=6.0,
                  position=11, stint_ends_on_lap=10, next_compound="RS",
                  laps_since_stop=2, last_said_lap=7, status_every_laps=1,
                  plan_binding_constraint="fuel", mandatory_stops_left=0,
                  fuel_capacity_l=100.0)
    fields.update(overrides)
    return RaceState(**fields)


def test_the_fuel_reaches_the_flag():
    state = after_the_stop()
    assert fuel_reaches_flag(state) is True
    assert 82.3 - 12 * 6.0 > 0, "the arithmetic this rests on"


def test_the_stop_is_no_longer_a_stop():
    assert stop_still_needed(after_the_stop()) is False


def test_he_is_told_once_and_it_outranks_the_box_call():
    call = next_call(after_the_stop())
    assert call is not None and call.kind == STOPS_OFF
    assert "fuelled to the flag" in call.call.lower()


def test_the_box_calls_stop_coming():
    """The four he ignored at Fuji. `laps_to_stop` of 0 is `_box_now`'s
    trigger and 1-2 is `_box_soon`'s, so both are exercised."""
    for lap, ends in ((10, 10), (9, 10), (8, 10)):
        state = after_the_stop(lap=lap, stint_ends_on_lap=ends,
                               stops_off_said=True)
        call = next_call(state)
        assert call is None or call.kind not in (BOX_NOW, BOX_SOON), \
            f"still boxing on lap {lap}: {call}"


# ------------------------------------------------------- what keeps a stop

def test_a_stop_the_rules_require_is_not_cancelled_by_a_tankful():
    """Fuji required one and he had taken it. Before that it stands however
    much fuel is aboard - a regulation is not answered by arithmetic."""
    assert stop_still_needed(after_the_stop(mandatory_stops_left=1)) is True


def test_a_stop_that_is_not_about_fuel_is_not_cancelled_by_fuel():
    """A tyre stop is a different claim. `binding_constraint` is the plan's
    own word for which kind its stops were."""
    assert stop_still_needed(after_the_stop(plan_binding_constraint="tyre")) \
        is True
    assert stop_still_needed(
        after_the_stop(plan_binding_constraint="evidence")) is True


def test_a_plan_that_does_not_say_keeps_its_stops():
    """§4.3. An unknown constraint is not a fuel constraint."""
    assert stop_still_needed(after_the_stop(plan_binding_constraint=None)) \
        is True


def test_no_burn_figure_keeps_the_stop():
    """`fuel_reaches_flag` is None there, and None is never read as yes."""
    state = after_the_stop(fuel_per_lap_l=None)
    assert fuel_reaches_flag(state) is None
    assert stop_still_needed(state) is True


def test_fuel_that_does_not_actually_reach_keeps_the_stop():
    thin = after_the_stop(fuel_l=30.0)
    assert fuel_reaches_flag(thin) is False
    assert stop_still_needed(thin) is True


# -------------------------------------------- the figure and its name agree

def test_cancelling_the_stop_moves_the_frame_to_the_flag():
    """**Rule 12 and 13 together.** The target and the words for it come out
    of one expression, so a cancelled stop cannot leave the driver hearing a
    figure measured against a distance nobody is driving to."""
    target, reference = fuel_frame(after_the_stop())
    assert reference == TO_THE_FLAG
    assert target == 12, "twelve laps of a twenty-lap race remain"


def test_while_the_stop_stands_the_frame_is_the_stop():
    target, reference = fuel_frame(after_the_stop(mandatory_stops_left=1))
    assert reference == TO_THE_STOP
    assert target == 2, "lap 8 of a stint ending on 10"
