"""The engineer's calls, and the coordinator that decides when to make them."""
from __future__ import annotations

import pytest

from pitcrew.race.calls import (
    BOX_NOW,
    BOX_SOON,
    CHEQUER,
    FUEL_LONG,
    FUEL_SHORT,
    GREEN,
    HIGH,
    LOW,
    STATUS,
    TYRE,
    Call,
    RaceState,
    _fuel,
    _fuel_gap,
    _fuel_instruction,
    clear_stint,

    next_call,
)
from pitcrew.race.coordinator import PlanContext, RaceCoordinator, RacePhase
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent


def a_state(**overrides) -> RaceState:
    fields = dict(lap=5, laps_total=20, fuel_l=40.0, fuel_per_lap_l=3.4,
                  position=3, stint_ends_on_lap=10, next_compound="RM",
                  laps_since_stop=5)
    fields.update(overrides)
    return RaceState(**fields)


def a_plan(stints=None) -> dict:
    return {"stints": stints or [
        {"laps": 10, "compound": "RM", "fuel_l": 37.4, "start_lap": 1},
        {"laps": 10, "compound": "RS", "fuel_l": 37.4, "start_lap": 11},
    ]}


def lap_event(lap_num: int, **overrides) -> SessionEvent:
    fields = dict(lap_num=lap_num, lap_time_ms=94_000, best_lap_ms=94_000,
                  delta_ms=0, fuel_start=40.0, fuel_end=36.6, fuel_used=3.4,
                  position=3, is_pit_lap=False, is_out_lap=False)
    fields.update(overrides)
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(**fields)})


# ------------------------------------------------------------------- form

def test_a_call_puts_the_instruction_before_the_reason():
    """Under a helmet at speed, the action has to arrive first."""
    call = Call(BOX_NOW, 10, "Box this lap.", "Fuel is the constraint.")
    assert call.spoken().startswith("Box this lap.")
    assert call.spoken().endswith("Fuel is the constraint.")


def test_low_confidence_is_said_out_loud():
    """'Unconfirmed' is a word the driver can act on."""
    call = Call(TYRE, 10, "Tyres are going.", "Modelled.", LOW)
    assert "Unconfirmed" in call.spoken()


def test_high_confidence_is_not_narrated():
    call = Call(BOX_NOW, 10, "Box this lap.", "On the plan.", HIGH)
    assert "confiden" not in call.spoken().lower()


def test_a_call_exports_with_its_reason_and_confidence():
    payload = Call(FUEL_SHORT, 4, "Map 3.", "1.2 short.", "medium").as_export()
    assert payload == {"lap": 4, "call": "Map 3.", "reason": "1.2 short.",
                       "confidence": "medium"}


# -------------------------------------------------------------- one at a time

def test_only_one_call_is_made_per_lap():
    """Two instructions at once is the same as none."""
    state = a_state(lap=10, fuel_l=1.0, wear_per_lap=0.2, laps_since_stop=10)
    call = next_call(state)
    assert call is not None
    assert isinstance(call, Call)


def test_boxing_outranks_fuel_saving():
    state = a_state(lap=10, fuel_l=2.0)
    assert next_call(state).kind == BOX_NOW


def test_a_call_is_not_repeated_every_lap():
    state = a_state(lap=5, fuel_l=2.0)
    first = next_call(state)
    state.said.append(first.kind)
    assert next_call(state) is None or next_call(state).kind != first.kind


def test_silence_is_a_valid_answer():
    """Six laps to the stop with six laps of fuel: nothing to report."""
    state = a_state(lap=4, fuel_l=6 * 3.4 + 1.0, stint_ends_on_lap=10)
    assert next_call(state) is None


# ------------------------------------------------------------------- boxing

def test_box_this_lap_names_the_compound_and_the_fuel():
    # 10 litres aboard, so the fill is a real instruction. With the default
    # 40 L the new sanity guard rightly says no fuel is needed - the tank
    # already covers the next stint - which is its own test below.
    state = a_state(lap=10, next_compound="RS", fuel_l=10.0)
    call = next_call(state)
    assert call.kind == BOX_NOW
    assert "RS" in call.call
    assert "litres" in call.reason


def test_a_fill_below_what_is_aboard_is_not_an_instruction():
    """"Fuel to 27 litres" was voiced with 51.9 L in the tank. GT7 cannot
    fill downwards, so obeying was impossible - the honest line is that the
    fuel is fine, which also says what the stop is for. And it must not
    open with "No fuel": under a helmet that phrase is an emergency until
    the second half of the sentence lands."""
    state = a_state(lap=10, next_compound="RS", fuel_l=51.9,
                    fuel_per_lap_l=6.79, next_stint_laps=3)
    call = next_call(state)
    assert call.kind == BOX_NOW
    assert "Fuel is fine" in call.reason
    assert not call.reason.startswith("No fuel")
    assert "litres" not in call.reason


def test_box_soon_counts_down():
    assert next_call(a_state(lap=8)).kind == BOX_SOON
    assert "Box in 2" in next_call(a_state(lap=8)).call
    assert "next lap" in next_call(a_state(lap=9)).call


def test_no_box_call_on_the_last_stint():
    """The last stint runs to the flag; there is no stop at the end of it."""
    state = a_state(lap=18, stint_ends_on_lap=None)
    call = next_call(state)
    assert call is None or call.kind != BOX_NOW


def test_no_box_call_while_in_the_pit():
    assert next_call(a_state(lap=10, in_pit=True)) is None


# --------------------------------------------------------------------- fuel

def test_short_on_fuel_asks_him_to_save_it():
    state = a_state(lap=5, fuel_l=10.0, stint_ends_on_lap=12)
    call = next_call(state)
    assert call.kind == FUEL_SHORT
    assert "Short-shift" in call.call
    assert "short" in call.reason


def test_fuel_in_hand_says_he_can_push():
    state = a_state(lap=5, fuel_l=60.0, stint_ends_on_lap=10)
    call = next_call(state)
    assert call.kind == FUEL_LONG
    assert "push" in call.call


def test_fuel_on_target_says_nothing():
    state = a_state(lap=5, fuel_l=5 * 3.4, stint_ends_on_lap=10)
    call = next_call(state)
    assert call is None or call.kind not in (FUEL_SHORT, FUEL_LONG)


def test_early_fuel_calls_carry_less_confidence():
    """Two laps of burn is not a fuel model."""
    state = a_state(lap=1, fuel_l=3.0, stint_ends_on_lap=12, laps_since_stop=1)
    assert next_call(state).confidence != HIGH


def test_no_fuel_call_without_a_burn_rate():
    state = a_state(lap=5, fuel_per_lap_l=None)
    call = next_call(state)
    assert call is None or call.kind not in (FUEL_SHORT, FUEL_LONG)


# -------------------------------------------------------------------- tyres

def test_the_tyre_call_is_always_low_confidence():
    """Wear is modelled, never measured. It must never sound like a reading."""
    state = a_state(lap=18, wear_per_lap=0.05, laps_since_stop=18,
                    stint_ends_on_lap=None, fuel_l=40.0)
    call = next_call(state)
    assert call.kind == TYRE
    assert call.confidence == LOW
    assert "Modelled" in call.reason


def test_no_tyre_call_without_a_wear_rate():
    state = a_state(lap=18, wear_per_lap=None, stint_ends_on_lap=None)
    call = next_call(state)
    assert call is None or call.kind != TYRE


def test_fresh_tyres_raise_nothing():
    state = a_state(lap=2, wear_per_lap=0.05, laps_since_stop=2,
                    stint_ends_on_lap=None, fuel_l=40.0)
    call = next_call(state)
    assert call is None or call.kind != TYRE


# ------------------------------------------------------------------- status

def test_a_status_call_comes_round_occasionally():
    # Last stint, fuel on target for the 15 laps remaining.
    state = a_state(lap=5, fuel_l=15 * 3.4 + 1.0, stint_ends_on_lap=None)
    call = next_call(state)
    assert call.kind == STATUS
    assert "P3" in call.call


def test_the_flag_is_called():
    state = a_state(lap=20, finished=True, position=2)
    call = next_call(state)
    assert call.kind == CHEQUER
    assert "P2" in call.reason


def test_green_is_called_at_the_start():
    state = a_state(lap=0, stint_ends_on_lap=None, fuel_l=None)
    call = next_call(state)
    assert call.kind == GREEN


# --------------------------------------------------------------- stint reset

def test_a_stop_lets_the_next_stint_speak_freshly():
    state = a_state(lap=10, said=[BOX_NOW, FUEL_SHORT], laps_since_stop=10)
    clear_stint(state, tyres_changed=True)
    assert BOX_NOW not in state.said
    assert state.laps_since_stop == 0


def test_a_fuel_only_stop_does_not_reset_the_tyre_model():
    """GT7 lets you take fuel without taking tyres.

    Treating every stop as a fresh set silenced the end-of-window call for a
    whole further stint - and the driver reads silence as nothing to report.
    """
    state = a_state(lap=10, said=[BOX_NOW], laps_since_stop=10)
    clear_stint(state, tyres_changed=False)
    assert BOX_NOW not in state.said            # the stint still speaks freshly
    assert state.laps_since_stop == 10          # but the set is the same set


def test_a_stop_that_says_nothing_about_the_tyres_says_so_out_loud():
    state = a_state(lap=18, laps_since_stop=18, wear_per_lap=0.05,
                    stint_ends_on_lap=None, fuel_l=40.0)
    clear_stint(state)
    assert state.laps_since_stop == 18
    call = next_call(state)
    assert call.kind == TYRE
    assert "may have changed" in call.reason
    assert "Unconfirmed." in call.spoken()


# --------------------------------------------------------------- coordinator

def a_context(**overrides) -> PlanContext:
    fields = dict(car="Porsche 911 RSR (991) '17", track="Fuji Speedway",
                  layout="Full", race_laps=20)
    fields.update(overrides)
    return PlanContext(**fields)


def test_arming_is_not_starting():
    """Nothing fires until the car is actually racing."""
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    assert race.arm(a_context(), a_context()) is True
    assert race.phase is RacePhase.ARMED
    assert race.running is False


def test_green_starts_the_race():
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    call = race.handle(SessionEvent(EventKind.RACE_STARTED,
                                    {"laps_in_race": 20}))
    assert race.running is True
    assert call.kind == GREEN


def test_a_race_that_starts_unarmed_is_not_ours():
    race = RaceCoordinator(a_plan())
    assert race.handle(SessionEvent(EventKind.RACE_STARTED, {})) is None
    assert race.running is False


def test_a_plan_for_a_different_car_is_refused():
    race = RaceCoordinator(a_plan())
    ok = race.arm(a_context(car="BMW M6 GT3"), a_context())
    assert ok is False
    assert "BMW M6 GT3" in race.refusal
    assert race.armed is False


def test_a_plan_for_a_different_race_length_is_refused():
    race = RaceCoordinator(a_plan())
    assert race.arm(a_context(race_laps=32), a_context()) is False
    assert "32 laps" in race.refusal


def test_a_plan_for_a_different_layout_is_refused():
    race = RaceCoordinator(a_plan())
    assert race.arm(a_context(layout="East"), a_context()) is False
    assert "East" in race.refusal


def test_laps_drive_the_plan():
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))

    calls = []
    for lap_num in range(1, 11):
        call = race.handle(lap_event(lap_num, fuel_end=40.0 - lap_num * 3.4))
        if call:
            calls.append(call)

    kinds = [c.kind for c in calls]
    assert BOX_SOON in kinds
    assert BOX_NOW in kinds
    assert kinds.index(BOX_SOON) < kinds.index(BOX_NOW)


def test_a_stop_advances_to_the_next_stint():
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    for lap_num in range(1, 11):
        race.handle(lap_event(lap_num))

    race.handle(SessionEvent(EventKind.PIT_ENTRY, {}))
    assert race.state.in_pit is True
    # Shaped like the real event: `session_state` always says whether the
    # tyres came off, and the coordinator used to throw that away.
    race.handle(SessionEvent(EventKind.PIT_EXIT,
                             {"fuel_added": 37.0, "tyres_changed": True}))

    assert race.state.in_pit is False
    assert race.state.stint_index == 1
    assert race.state.laps_since_stop == 0
    # The last stint runs to the flag, so there is no further stop.
    assert race.state.stint_ends_on_lap is None


def test_a_fuel_only_stop_keeps_the_tyre_count_running():
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4, wear_per_lap=0.05)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    for lap_num in range(1, 11):
        race.handle(lap_event(lap_num))

    race.handle(SessionEvent(EventKind.PIT_ENTRY, {}))
    race.handle(SessionEvent(EventKind.PIT_EXIT,
                             {"fuel_added": 37.0, "tyres_changed": False}))

    assert race.state.stint_index == 1          # the plan still advances
    assert race.state.laps_since_stop == 10     # the rubber did not


def test_the_snapshot_is_what_the_pit_wall_shows():
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    race.handle(lap_event(4, fuel_end=26.0))

    snapshot = race.snapshot()
    assert snapshot["lap"] == 4
    assert snapshot["lapsRemaining"] == 16
    assert snapshot["lapsToStop"] == 6
    assert snapshot["lapsOfFuel"] == pytest.approx(26.0 / 3.4, abs=0.1)
    assert snapshot["nextCompound"] == "RS"


def test_the_flag_ends_the_race():
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    call = race.handle(SessionEvent(EventKind.RACE_FINISHED,
                                    {"laps": 20, "position": 2}))
    assert race.phase is RacePhase.FINISHED
    assert call.kind == CHEQUER


def test_a_race_with_no_plan_still_runs():
    """No approved plan is a reason to say less, not to refuse to race."""
    race = RaceCoordinator(None, fuel_per_lap_l=3.4)
    assert race.arm(None, a_context()) is True
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    race.handle(lap_event(5, fuel_end=30.0))
    assert race.snapshot()["lapsToStop"] is None


def test_no_push_call_at_the_start_of_a_stint():
    """The tank was just filled; surplus then says nothing about pace."""
    state = a_state(lap=1, laps_since_stop=1, fuel_l=90.0,
                    stint_ends_on_lap=16)
    call = next_call(state)
    assert call is None or call.kind != FUEL_LONG


def test_the_push_call_arrives_late_in_a_stint():
    state = a_state(lap=13, laps_since_stop=13, fuel_l=40.0,
                    stint_ends_on_lap=16)
    call = next_call(state)
    assert call.kind == FUEL_LONG


def test_fuel_calls_switch_to_the_races_own_burn_rate():
    """Practice said 3.4; this race is burning 4.6. Advising on the practice
    figure would tell him he can push while he is running dry."""
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))

    for lap_num in range(1, 5):
        race.handle(lap_event(lap_num, fuel_used=4.6,
                              fuel_end=92.0 - lap_num * 4.6))

    assert race.observed_fuel_per_lap() == pytest.approx(4.6)
    assert race.state.fuel_per_lap_l == pytest.approx(4.6)
    assert race.planned_fuel_per_lap_l == pytest.approx(3.4)


def test_one_odd_lap_does_not_move_the_burn_rate():
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    for used in (3.4, 3.4, 0.9, 3.5):
        race.handle(lap_event(1, fuel_used=used))
    assert race.state.fuel_per_lap_l == pytest.approx(3.4)


def test_the_practice_rate_stands_until_the_race_shows_its_own():
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    race.handle(lap_event(1, fuel_used=4.6))
    assert race.observed_fuel_per_lap() is None
    assert race.state.fuel_per_lap_l == pytest.approx(3.4)


def test_accepting_a_run_to_the_flag_removes_the_stop():
    """Keeping the running stint would leave the stop he just cancelled."""
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    for lap_num in range(1, 7):
        race.handle(lap_event(lap_num))
    assert race.stops_planned() == 1

    race.adopt((14,))
    assert race.stops_planned() == 0
    assert race.state.stint_ends_on_lap is None


def test_accepting_an_extra_stop_adds_one():
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    for lap_num in range(1, 7):
        race.handle(lap_event(lap_num))

    race.adopt((7, 7))
    assert race.stops_planned() == 1
    assert race.state.stint_ends_on_lap == 13


# --------------------------------------------- the fuel figure is executable
#
# Regression for the audit's D1. `_fuel_instruction` had no tank clamp and
# `RaceState` carried no capacity, so the engineer would ask for a fill the
# car physically cannot take - spoken at HIGH confidence, inside a box-now
# call, under a helmet.

def test_the_fuel_call_is_clamped_to_the_tank():
    """A 15-lap stint at 10 L a lap does not fit a 100 L tank."""
    state = RaceState(lap=5, laps_total=60, fuel_l=40.0, fuel_per_lap_l=10.0,
                      stint_ends_on_lap=10, next_stint_laps=15,
                      fuel_capacity_l=100.0)
    said = _fuel_instruction(state)
    assert "510" not in said                      # what it used to say
    assert said == "Fuel to full. Still 6.0 laps short."


def test_a_normal_fill_is_still_a_number_of_litres():
    state = RaceState(lap=5, laps_total=20, fuel_l=40.0, fuel_per_lap_l=5.0,
                      stint_ends_on_lap=10, next_stint_laps=10,
                      fuel_capacity_l=100.0)
    assert _fuel_instruction(state) == "Fuel to 55 litres."


def test_the_shortfall_is_the_call_when_the_clamp_binds():
    """"Fill it and you are still two laps short" is actionable.

    "Fuel to 510 litres" is not: the driver acts on it, finds the fill stops
    early, and has to work out the shortfall himself at pit-exit speed.

    The target is **the stint after the stop**. This test used to spell out
    the fill-to-the-flag arithmetic - 25 laps of race after a stop on lap 5 -
    and assert it, which is defect S1 rather than the clamp the test was
    written for.
    """
    state = RaceState(lap=1, laps_total=60, fuel_l=50.0, fuel_per_lap_l=6.0,
                      stint_ends_on_lap=20, next_stint_laps=20,
                      fuel_capacity_l=100.0)
    said = _fuel_instruction(state)
    assert "short" in said
    # 20 laps in the next stint, +1 reserve = 126 L wanted from a 100 L tank,
    # so 26 L over, which is 4.3 laps at 6 L a lap.
    assert "4.3 laps short" in said


def test_an_unknown_capacity_does_not_invent_a_clamp():
    """No capacity is not a 0 L tank. The old behaviour stands."""
    state = RaceState(lap=5, laps_total=60, fuel_l=40.0, fuel_per_lap_l=10.0,
                      stint_ends_on_lap=10, fuel_capacity_l=None)
    assert _fuel_instruction(state) == "Fuel to 510 litres."


def test_no_box_now_call_ever_asks_for_more_than_the_tank():
    """The class, not the instance, across a spread of race shapes."""
    for laps_total, burn, capacity in ((60, 10.0, 100.0), (30, 6.0, 100.0),
                                       (45, 3.0, 60.0), (12, 9.0, 45.0)):
        for ends_on in range(1, laps_total):
            state = RaceState(lap=ends_on, laps_total=laps_total,
                              fuel_l=10.0, fuel_per_lap_l=burn,
                              stint_ends_on_lap=ends_on,
                              fuel_capacity_l=capacity)
            said = _fuel_instruction(state)
            if "litres" not in said:
                continue
            asked = float(said.split("Fuel to ")[1].split(" litres")[0])
            assert asked <= capacity, f"{said} into a {capacity:.0f} L tank"


# --------------------------------------------- the fill is for the next stint
#
# Regression for S1. `_fuel_instruction` computed the fill as everything from
# the stop to the flag, so at stop 1 of a two-stop the driver was told to take
# fuel for the whole rest of the race - and where the tank could not hold it,
# was told he was short of a target nobody was aiming at.

def test_the_stop_fills_for_the_next_stint_not_for_the_rest_of_the_race():
    """Three stints of 10 laps at 3.4 L: stop 1 takes 37 L, not 71."""
    state = RaceState(lap=10, laps_total=30, fuel_l=1.0, fuel_per_lap_l=3.4,
                      stint_ends_on_lap=10, next_stint_laps=10,
                      fuel_capacity_l=100.0)
    assert _fuel_instruction(state) == "Fuel to 37 litres."


def test_the_fill_uses_the_races_own_burn_and_not_the_planned_litres():
    """The plan says 34 L; this race is burning 4.6 a lap, so it is 50."""
    state = RaceState(lap=10, laps_total=30, fuel_l=1.0, fuel_per_lap_l=4.6,
                      stint_ends_on_lap=10, next_stint_laps=10,
                      fuel_capacity_l=100.0)
    assert _fuel_instruction(state) == "Fuel to 51 litres."


def test_the_plan_carries_the_next_stints_length_into_the_call():
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(a_context(), a_context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    assert race.state.next_stint_laps == 10
    race.handle(SessionEvent(EventKind.PIT_EXIT,
                             {"fuel_added": 37.0, "tyres_changed": True}))
    # The last stint runs to the flag; there is no stop after it to fuel for.
    assert race.state.next_stint_laps is None


# ------------------------------------------------- overdue is not fuel in hand
#
# Regression for S2, the most dangerous sentence the app can say.

def test_a_stop_is_never_a_negative_number_of_laps_away():
    state = a_state(lap=13, stint_ends_on_lap=10)
    assert state.laps_to_stop() == 0
    assert state.past_box_lap is True


def test_overdue_laps_are_not_counted_as_fuel_in_hand():
    """Box was lap 10 and it is lap 13 with 3 litres left.

    `laps_to_stop` returned -3, and -3 came off the fuel gap as three laps of
    surplus: "You can push. 2.9 laps of fuel in hand." at HIGH confidence with
    0.88 laps aboard. Flooring at zero alone does not fix it - a target of
    zero makes the gap the whole tank and the same call fires harder.
    """
    state = a_state(lap=13, fuel_l=3.0, stint_ends_on_lap=10,
                    laps_since_stop=13)
    assert _fuel_gap(state) == pytest.approx(3.0 / 3.4 - 7)
    assert _fuel(state).kind == FUEL_SHORT
    assert next_call(state).kind == BOX_NOW      # boxing outranks the fuel call


# --------------------------------------------- the lever is the shift, not a map
#
# He runs fuel map 1 only and has tested why: a map step costs more lap time
# than the fuel it saves, against short-shifting, lift-and-coast or a tow. His
# own test is primary evidence, so `fuel_map_for` is gone and the shortfall is
# answered in the lever he actually uses.

def test_a_fuel_shortfall_asks_for_a_short_shift_and_not_a_map():
    state = a_state(lap=5, fuel_l=20.0, stint_ends_on_lap=15,
                    laps_since_stop=5, short_shift_l_per_1000rpm=1.762)
    call = _fuel(state)
    assert call.kind == FUEL_SHORT
    assert call.call.startswith("Short-shift ")
    assert "Map" not in call.call and "map" not in call.reason
    assert "laps short on fuel" in call.reason


def test_the_rpm_drop_follows_from_the_size_of_the_shortfall():
    """A fixed drop answers one shortfall and no other - the same fault the
    fixed "Map 3" had. The conversion is the car's own measured slope."""
    def drop_for(fuel_l):
        state = a_state(lap=5, fuel_l=fuel_l, stint_ends_on_lap=15,
                        laps_since_stop=5, short_shift_l_per_1000rpm=1.762)
        return int(_fuel(state).call.split()[-1].rstrip("."))

    small, large = drop_for(30.0), drop_for(24.0)
    assert 0 < small < large, (small, large)


def test_a_shortfall_short_shifting_cannot_cover_says_what_is_left():
    """Past the cap it is a box decision, not a saving one - and the laps it
    still cannot cover are the useful half of the call."""
    state = a_state(lap=5, fuel_l=8.0, stint_ends_on_lap=25,
                    laps_since_stop=5, short_shift_l_per_1000rpm=1.762)
    call = _fuel(state)
    assert call.kind == FUEL_SHORT
    assert "Still" in call.reason and "short after it" in call.reason


def test_a_car_with_no_measured_slope_names_the_lever_without_a_number():
    """The lever is still his. The number would be fabricated."""
    state = a_state(lap=5, fuel_l=20.0, stint_ends_on_lap=15,
                    laps_since_stop=5, short_shift_l_per_1000rpm=None)
    call = _fuel(state)
    assert call.kind == FUEL_SHORT
    assert call.call == "Short-shift and lift into the slow corners."
    assert not any(ch.isdigit() for ch in call.call)


def test_the_drop_is_rounded_because_he_is_reading_a_beep():
    """The fit's own interval is [0.92, 2.60] L per 1000 rpm, so an rpm-exact
    drop would imply a precision that does not exist."""
    state = a_state(lap=5, fuel_l=20.0, stint_ends_on_lap=15,
                    laps_since_stop=5, short_shift_l_per_1000rpm=1.762)
    drop = int(_fuel(state).call.split()[-1].rstrip("."))
    assert drop % 50 == 0, drop


# ------------------------------------------------- a worsening call is repeated
#
# Regression for S5. `next_call`'s docstring has always promised re-issue
# "unless it has become more urgent" and nothing implemented it: a shortfall
# warned at 3.8 laps was met with silence at 4.9, 5.9 and 7.0.

def test_a_worsening_fuel_shortfall_is_said_again():
    state = a_state(lap=6, fuel_l=10.0, stint_ends_on_lap=12,
                    laps_since_stop=6)
    first = next_call(state)
    assert first.kind == FUEL_SHORT
    state.record(first)

    assert next_call(state) is None          # nothing has changed: say nothing

    state.fuel_l = 2.0                       # another lap and a half missing
    again = next_call(state)
    assert again.kind == FUEL_SHORT
    assert again.severity > first.severity


def test_a_shortfall_that_barely_moves_is_not_repeated():
    state = a_state(lap=6, fuel_l=10.0, stint_ends_on_lap=12,
                    laps_since_stop=6)
    state.record(next_call(state))
    state.fuel_l = 9.5                       # 0.15 of a lap: not worth saying
    assert next_call(state) is None


def test_the_status_call_comes_round_more_than_once():
    """`STATUS_EVERY_LAPS` is this call's rate limiter, and it could only
    ever match once while the kind was suppressed for the whole stint."""
    state = a_state(lap=5, fuel_l=15 * 3.4 + 1.0, stint_ends_on_lap=None)
    first = next_call(state)
    assert first.kind == STATUS
    state.record(first)

    state.lap = 10
    state.fuel_l = 10 * 3.4 + 1.0
    assert next_call(state).kind == STATUS
