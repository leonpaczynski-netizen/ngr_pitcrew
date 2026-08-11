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
    state = a_state(lap=10, next_compound="RS")
    call = next_call(state)
    assert call.kind == BOX_NOW
    assert "RS" in call.call
    assert "litres" in call.reason


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

def test_short_on_fuel_asks_for_a_leaner_map():
    state = a_state(lap=5, fuel_l=10.0, stint_ends_on_lap=12)
    call = next_call(state)
    assert call.kind == FUEL_SHORT
    assert "Map" in call.call
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
    clear_stint(state)
    assert BOX_NOW not in state.said
    assert state.laps_since_stop == 0


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
    race.handle(SessionEvent(EventKind.PIT_EXIT, {"fuel_added": 37.0}))

    assert race.state.in_pit is False
    assert race.state.stint_index == 1
    assert race.state.laps_since_stop == 0
    # The last stint runs to the flag, so there is no further stop.
    assert race.state.stint_ends_on_lap is None


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
