"""A crossing already made in the box is not taken off the fill.

The critic's replay of the live rows, 7 Sep 2026: at Daytona (s127) and Spa
(s112) the start/finish line is inside the pit lane BEFORE the box, so the lap
counter moves before the hose goes in and the lap in progress is the out-lap,
run in full. `_laps_after_this_stop` took a lap off whenever `in_pit`, which
was right at Deep Forest and Monza (line after the box) and one lap short at
the other two - 54.5 L for 8 laps at Daytona, on the plan approved for that
night. A lap over is standing time; a lap under is a DNF.
"""
from __future__ import annotations

from pitcrew.race.calls import RaceState, fuel_target_basis, fuel_target_l
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent


def _lap(num: int, fuel_end: float, used: float = 7.78, pit=False):
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(
        lap_num=num, lap_time_ms=104_500, best_lap_ms=104_000,
        delta_ms=500, fuel_start=fuel_end + used, fuel_end=fuel_end,
        fuel_used=used, position=4, is_pit_lap=pit, is_out_lap=False)})


def _daytona():
    """11 + 9 on a 20-lap race, the plan approved for 7 Sep."""
    plan = {"stops": 1, "pit_laps": [11], "laps": 20,
            "stints": [{"laps": 11, "compound": "RS", "fuel_l": 85.4,
                        "start_lap": 1, "tyres": True},
                       {"laps": 9, "compound": "RS", "fuel_l": 69.4,
                        "start_lap": 12, "tyres": True}]}
    race = RaceCoordinator(plan, fuel_per_lap_l=7.78)
    context = PlanContext(car="Lamborghini Huracán GT3 '15",
                          track="Daytona International Speedway",
                          layout="Road Course", race_laps=20)
    assert race.arm(context, context) is True
    race.handle(SessionEvent(EventKind.RACE_STARTED, {}))
    fuel = 100.0
    for n in range(1, 12):
        fuel -= 7.78
        race.handle(_lap(n, fuel))
    race.state.fuel_per_lap_l = 7.78
    return race, fuel


def _laps_covered(state: RaceState) -> float:
    return fuel_target_l(state) / state.fuel_per_lap_l


def test_at_daytona_the_line_is_crossed_before_the_fill_and_the_fill_is_not_cut():
    race, fuel = _daytona()
    race.handle(SessionEvent(EventKind.PIT_ENTRY, {"fuel": fuel}))
    # The line inside the lane: lap 12 completes with the car in the box.
    race.handle(_lap(12, fuel - 0.5, used=0.5, pit=True))
    state = race.state
    assert state.in_pit and state.crossed_in_box
    # 8 laps to run (13-20), every one of them whole.
    assert 8 <= _laps_covered(state) < 9.5
    assert fuel_target_basis(state) == "8 laps to the flag"


def test_at_deep_forest_the_line_comes_after_the_box_and_the_lap_in_progress_is_cut():
    race, fuel = _daytona()
    race.handle(SessionEvent(EventKind.PIT_ENTRY, {"fuel": fuel}))
    state = race.state
    assert state.in_pit and not state.crossed_in_box
    # Lap 12 is in progress and mostly driven: 20 - 11 = 9 remaining, less one.
    assert 8 <= _laps_covered(state) < 9.5
    assert fuel_target_basis(state) == "8 laps after the box"


def test_the_flag_frame_is_used_once_the_counts_agree():
    """Before the crossing the fill says 'after the box' - never 'to the
    flag' with a count the heartbeat's 'to go' would contradict."""
    race, fuel = _daytona()
    race.handle(SessionEvent(EventKind.PIT_ENTRY, {"fuel": fuel}))
    before = fuel_target_basis(race.state)
    race.handle(_lap(12, fuel - 0.5, used=0.5, pit=True))
    after = fuel_target_basis(race.state)
    assert before.endswith("after the box")
    assert after.endswith("to the flag")
    assert before.split()[0] == after.split()[0] == "8"


def test_pit_exit_clears_the_flag_for_the_next_stop():
    race, fuel = _daytona()
    race.handle(SessionEvent(EventKind.PIT_ENTRY, {"fuel": fuel}))
    race.handle(_lap(12, fuel - 0.5, used=0.5, pit=True))
    race.handle(SessionEvent(EventKind.PIT_EXIT, {"fuel_added": 60.0,
                                                  "tyres_changed": True}))
    assert race.state.crossed_in_box is False
    assert race.state.in_pit is False


# ------------------------------------------------------------- tyres field

def test_a_tyres_field_in_quotes_is_refused_at_the_door():
    from pitcrew.strategy.handover import from_dict

    handover = from_dict({"stops": 1, "stints": [
        {"laps": 11, "compound": "RS", "fuel_l": 85.4, "start_lap": 1},
        {"laps": 9, "compound": "RS", "fuel_l": 69.4, "start_lap": 12,
         "tyres": "false"}], "playbook": []})
    problems = handover.validate()
    assert any("tyres='false'" in p for p in problems)


def test_a_tyres_field_in_quotes_is_unsaid_not_true_if_it_reaches_the_race():
    from pitcrew.race.coordinator import _tri

    assert _tri("false") is None
    assert _tri("true") is None
    assert _tri(0) is False and _tri(1) is True
    assert _tri(True) is True and _tri(None) is None


# --------------------------------------------------------------- fallback

def test_the_fallback_never_says_a_negative_number_of_laps():
    state = RaceState(lap=5, laps_total=None, fuel_per_lap_l=10.0,
                      fuel_l=40.0, stint_ends_on_lap=10)
    assert fuel_target_l(state) is None
    assert fuel_target_basis(state) is None
