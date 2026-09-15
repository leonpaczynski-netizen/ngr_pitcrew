"""Fuel-save stints, the beep George moves on fuel, and the race's lap ceiling.

Sardegna race sim, session 177, 15 Sep 2026. He crossed the line to start
lap 29 with 3.1 s on the clock, so a 50-minute race at that pace is never 30
laps - and George still asked for 96 L at the stop where 15 laps at the burn
he had installed wanted 82.8 L: laps the clock could not hold, and a whole
spare lap on top because the count was "not firm". The driver, same day:

    "the race can never be more than 29 laps so never put more fuel in than
    that ... write the fuel save into George ... if we have more fuel on board
    then we need in last stint to flag he can change the shift beep for full
    performance or like wise if we under fueled change the shift beep to fuel
    save"

Three pieces, one test group each: the plan contract (`handover`), the gate
(`certify`), and George (`calls.fuel_mode_wanted`, the coordinator's ceiling
and the beep it follows).
"""
from __future__ import annotations

from pitcrew.race.calls import (
    FUEL_MODE,
    FUEL_MODE_DROP_RPM,
    FUEL_MODE_FULL_REACHES,
    FUEL_MODE_FULL_SHORT,
    FUEL_MODE_PLANNED,
    RaceState,
    STATUS,
    Call,
    fuel_mode_wanted,
    next_call,
)
from pitcrew.race.coordinator import RaceCoordinator
from pitcrew.strategy.certify import certify
from pitcrew.strategy.handover import fuel_plan_problems, from_dict
from pitcrew.strategy.model import RaceInputs


BURNS = {"save": 5.25, "full": 6.75}


def sardegna_plan(**over) -> dict:
    """The driver's plan: RM 12, RH 17, both at the fuel-save beep."""
    plan = {
        "stops": 1, "pit_laps": [12], "laps": 29, "max_race_laps": 29,
        "fuel_burns": dict(BURNS),
        "stints": [
            {"laps": 12, "compound": "RM", "fuel_l": 100.0, "start_lap": 1,
             "fuel_save": True},
            {"laps": 17, "compound": "RH", "fuel_l": 95.0, "start_lap": 13,
             "tyres": True, "fuel_save": True},
        ],
    }
    plan.update(over)
    return plan


# ------------------------------------------------------------ the contract


def test_the_drivers_plan_is_a_valid_handover():
    payload = {**sardegna_plan(), "playbook": [], "author": "ludo"}
    assert from_dict(payload).validate() == []


def test_a_fuel_save_stint_needs_the_measured_saving_burn():
    plan = sardegna_plan()
    del plan["fuel_burns"]
    problems = fuel_plan_problems(plan)
    assert any("fuel-save" in p and "fuel_burns" in p for p in problems)


def test_a_saving_burn_at_or_above_the_full_burn_is_two_columns_transposed():
    problems = fuel_plan_problems(
        sardegna_plan(fuel_burns={"save": 6.75, "full": 5.25}))
    assert any("below" in p for p in problems)


def test_stints_past_the_ceiling_are_refused_by_name():
    plan = sardegna_plan(max_race_laps=28)
    assert any("can never run more than 28" in p
               for p in fuel_plan_problems(plan))


def test_a_fuel_save_flag_that_is_not_a_yes_or_no_is_refused():
    plan = sardegna_plan()
    plan["stints"][0]["fuel_save"] = "yes"
    assert any("fuel_save" in p for p in fuel_plan_problems(plan))


def test_a_plan_with_none_of_it_has_no_problems():
    assert fuel_plan_problems({"stints": [{"laps": 10}]}) == []


# ---------------------------------------------------------------- the gate


def sardegna_inputs(**over) -> RaceInputs:
    base = dict(race_laps=29, lap_time_ms=102_672, race_minutes=50.0,
                fuel_capacity_l=100.0, fuel_per_lap_l=5.586,
                refuel_rate_lps=1.0, pit_loss_s=34.5, wear_per_lap=None,
                available_compounds=("RH", "RM", "RS"),
                required_compounds=())
    base.update(over)
    return RaceInputs(**base)


def test_a_fuel_save_stint_is_reached_on_the_saving_burn():
    """17 laps at the event burn plus its reserve lap is over the tank; at the
    measured saving burn it is not. The same stint unflagged is still refused -
    the flag is the claim, and the claim needs its burn."""
    saving = certify(sardegna_plan(), sardegna_inputs())
    assert not any("tank that reaches" in r for r in saving.refusals)

    unflagged = sardegna_plan()
    for stint in unflagged["stints"]:
        stint.pop("fuel_save")
    plain = certify(unflagged, sardegna_inputs())
    assert any("stint 2 runs 17 laps on a tank that reaches" in r
               for r in plain.refusals)


def test_the_ceiling_turns_a_one_lap_clock_overshoot_into_a_warning():
    """The clock model charges each stop its whole load and allows about 28;
    the driver's measured crossing says 29 is the most there can be, and the
    fill is sized live against that ceiling - so it is said, not refused."""
    got = certify(sardegna_plan(), sardegna_inputs())
    assert not any("the clock allows about" in r for r in got.refusals)
    assert any("never run more than 29" in w for w in got.warnings)


def test_without_a_ceiling_the_clock_still_refuses():
    plan = sardegna_plan()
    del plan["max_race_laps"]
    got = certify(plan, sardegna_inputs())
    assert any("the clock allows about" in r for r in got.refusals)


# ------------------------------------------------------ George: the decision


def last_stint(**over) -> RaceState:
    """Stint 2, to the flag: 10 laps left, the count firm at the ceiling."""
    base = dict(lap=19, laps_total=29, fuel_l=60.0, fuel_per_lap_l=5.3,
                fuel_capacity_l=100.0, race_minutes=50.0,
                laps_estimate_firm=True, stint_index=1, fuel_sd_l=0.126,
                fuel_save_engaged=True, fuel_save_planned=True)
    base.update(over)
    return RaceState(**base)


def test_surplus_to_the_flag_at_full_revs_releases_the_beep():
    # 10 laps x 5.4 at full revs = 54 L; 60 L aboard.
    engaged, why, _litres = fuel_mode_wanted(
        last_stint(), save_burn_l=5.0, full_burn_l=5.4)
    assert engaged is False and why == FUEL_MODE_FULL_REACHES


def test_not_enough_for_full_revs_holds_the_saving_beep():
    engaged, why, _litres = fuel_mode_wanted(
        last_stint(fuel_l=55.0), save_burn_l=5.25, full_burn_l=6.75)
    assert engaged is True and why is None


def test_running_full_and_falling_short_puts_the_saving_beep_back():
    engaged, why, litres = fuel_mode_wanted(
        last_stint(fuel_save_engaged=False, fuel_l=60.0),
        save_burn_l=5.25, full_burn_l=6.75)
    assert engaged is True and why == FUEL_MODE_FULL_SHORT
    assert litres is not None and litres > 0


def test_it_does_not_flap_on_a_litre_either_side():
    """Released only with the hysteresis in hand; held full until the full
    burn genuinely no longer reaches (CLAUDE.md rule 10's two-sided bound)."""
    from pitcrew.race.calls import FUEL_MODE_HYSTERESIS_L
    from pitcrew.strategy.model import fuel_margin_l

    margin, _ = fuel_margin_l(10, 6.0, sd_l=0.126, timed=True,
                              lap_count_firm=True)
    reaches_exactly = 10 * 6.0 + margin
    inside = reaches_exactly + FUEL_MODE_HYSTERESIS_L / 2
    engaged, _why, _ = fuel_mode_wanted(last_stint(fuel_l=inside),
                                        save_burn_l=5.0, full_burn_l=6.0)
    assert engaged is True
    engaged, _why, _ = fuel_mode_wanted(
        last_stint(fuel_l=inside, fuel_save_engaged=False),
        save_burn_l=5.0, full_burn_l=6.0)
    assert engaged is False
    engaged, why, _ = fuel_mode_wanted(
        last_stint(fuel_l=reaches_exactly + FUEL_MODE_HYSTERESIS_L + 0.01),
        save_burn_l=5.0, full_burn_l=6.0)
    assert engaged is False and why == FUEL_MODE_FULL_REACHES


def test_a_planned_saving_stint_to_a_stop_holds_the_saving_beep():
    """Surplus to the STOP is not spare fuel: it has to be put back in at the
    pump, and saving on the mediums is also saving the mediums."""
    state = RaceState(lap=3, laps_total=29, fuel_l=85.0, fuel_per_lap_l=5.3,
                      fuel_capacity_l=100.0, race_minutes=50.0,
                      stint_index=0, stint_ends_on_lap=12,
                      further_stop_planned=False,
                      fuel_save_engaged=True, fuel_save_planned=True)
    engaged, why, _ = fuel_mode_wanted(state, save_burn_l=5.25,
                                       full_burn_l=6.75)
    assert engaged is True and why is None


def test_an_unmanaged_race_is_left_exactly_as_it_was():
    state = last_stint(fuel_save_engaged=None)
    assert fuel_mode_wanted(state, save_burn_l=5.0,
                            full_burn_l=5.4) == (None, None, None)


def test_with_no_full_burn_to_price_it_the_saving_beep_stays():
    """Never assume: the switch to full revs needs a full-revs burn."""
    engaged, why, _ = fuel_mode_wanted(last_stint(), save_burn_l=5.0,
                                       full_burn_l=None)
    assert engaged is True and why is None


# --------------------------------------------------- George: the coordinator


def test_the_plan_arms_the_saving_beep_from_the_first_stint():
    race = RaceCoordinator(sardegna_plan(), fuel_per_lap_l=5.3,
                           fuel_capacity_l=100.0)
    assert race.state.fuel_save_engaged is True
    assert race.state.fuel_save_planned is True
    assert race.beep_drop_rpm() == FUEL_MODE_DROP_RPM


def test_a_plan_that_says_nothing_about_saving_changes_nothing():
    plan = {"stints": [{"laps": 10, "compound": "RH", "fuel_l": 60.0}]}
    race = RaceCoordinator(plan, fuel_per_lap_l=6.0, fuel_capacity_l=100.0)
    assert race.state.fuel_save_engaged is None
    assert race.beep_drop_rpm() is None
    asked = Call("fuel-short", 3, "Short-shift 450.", "",
                 short_shift_drop_rpm=450.0)
    assert race.beep_drop_rpm(asked) == 450.0


def test_a_call_that_asks_for_nothing_does_not_release_a_planned_save():
    """The defect that would have undone the whole plan: any call without a
    drop used to be read as "stop short-shifting"."""
    race = RaceCoordinator(sardegna_plan(), fuel_per_lap_l=5.3,
                           fuel_capacity_l=100.0)
    box = Call("box-soon", 11, "Box next lap.", "")
    assert race.beep_drop_rpm(box) == FUEL_MODE_DROP_RPM
    race.state.fuel_save_engaged = False
    assert race.beep_drop_rpm(box) is None


def test_the_mode_constant_is_the_beeps_own_default():
    from pitcrew.engineer.shift_beep import DEFAULT_SHORT_SHIFT_DROP_RPM
    assert FUEL_MODE_DROP_RPM == DEFAULT_SHORT_SHIFT_DROP_RPM


class _Clock:
    """Just enough of `RaceClock` for `_update_clock_distance`."""

    running = True
    corroborated = True
    laps_dropped = 0

    def __init__(self, remaining_s: float, lap_s: float) -> None:
        self.remaining_s = remaining_s
        self._lap_s = lap_s

    def laps_left(self, lap_ms, less_s: float = 0.0):
        import math
        return max(0, math.ceil((self.remaining_s - less_s) / self._lap_s))

    def laps_left_margin_s(self, lap_ms):
        return 0.1   # inside any lap-time noise: NOT firm on its own


def _timed_race(remaining_s: float, *, lap: int, plan=None) -> RaceCoordinator:
    race = RaceCoordinator(plan or sardegna_plan(), fuel_per_lap_l=5.52,
                           fuel_capacity_l=100.0, lap_time_ms=102_500)
    race.state.race_minutes = 50.0
    race.state.lap = lap
    race.clock = _Clock(remaining_s, 102.5)
    race.expect.achieved_lap_time_ms = lambda: 102_500
    race.expect.sigma_ms = lambda: 900.0
    return race


def test_the_ceiling_caps_the_laps_the_fill_is_sized_for():
    """Session 177 at the end of lap 13: 1,653 s on the clock is 17 laps by
    `ceil(time / lap)`, and 29 - 13 is 16. George counts 16."""
    race = _timed_race(1653.0, lap=13)
    race._update_clock_distance()
    assert race.state.laps_total == 29
    assert race.state.laps_remaining() == 16
    assert race.state.laps_after_stops is None or \
        race.state.laps_after_stops <= 16


def test_at_the_ceiling_the_count_is_firm_so_no_spare_lap_is_carried():
    race = _timed_race(1653.0, lap=13)
    race._update_clock_distance()
    assert race.state.laps_estimate_firm is True


def test_below_the_ceiling_the_clock_still_counts():
    race = _timed_race(900.0, lap=20)   # 9 laps by the clock, 9 to the ceiling
    race._update_clock_distance()
    assert race.state.laps_total == 29
    race = _timed_race(700.0, lap=20)   # 7 by the clock: the race is shorter
    race._update_clock_distance()
    assert race.state.laps_total == 27


def test_the_ceiling_is_the_flag():
    race = _timed_race(120.0, lap=29)
    race._update_clock_distance()
    assert race.state.finished is True


def test_the_mode_change_is_said_once_and_moves_the_beep():
    state = last_stint(fuel_save_engaged=False, fuel_save_planned=True)
    state.fuel_mode_change = (19, False, FUEL_MODE_FULL_REACHES, 6.0)
    call = next_call(state)
    assert call is not None and call.kind == FUEL_MODE
    assert call.short_shift_drop_rpm is None
    assert "Full" in call.call
    state.record(call)
    assert state.fuel_mode_change is None
    assert call.kind != STATUS


def test_the_planned_saving_beep_is_named_as_planned():
    state = last_stint(lap=13, fuel_l=95.0)
    state.fuel_mode_change = (13, True, FUEL_MODE_PLANNED, None)
    call = next_call(state)
    assert call is not None and call.kind == FUEL_MODE
    assert call.short_shift_drop_rpm == FUEL_MODE_DROP_RPM


def test_the_beep_plays_the_issued_fuel_points_through_a_box_call():
    """End to end through the beep: Sardegna's table, 8,500 performance and
    7,400 fuel-saving. A box call on the in-lap must not put 8,500 back."""
    from pitcrew.engineer.shift_beep import ShiftBeep

    beep = ShiftBeep(per_gear={3: 8500.0})
    beep.short_shift_drop_per_gear = {3: 1100.0}   # 8,500 - 7,400, as issued

    def set_short_shift(drop_rpm):                 # the bridge's own two lines
        if drop_rpm and drop_rpm > 0:
            beep.short_shift_drop_rpm = float(drop_rpm)
            beep.short_shifting = True
        else:
            beep.short_shifting = False

    race = RaceCoordinator(sardegna_plan(), fuel_per_lap_l=5.3,
                           fuel_capacity_l=100.0)
    set_short_shift(race.beep_drop_rpm())
    assert beep.threshold_for(3) == 7400.0
    set_short_shift(race.beep_drop_rpm(Call("box-now", 12, "Box this lap.", "")))
    assert beep.threshold_for(3) == 7400.0
    race.state.fuel_save_engaged = False            # George: fuel reaches
    set_short_shift(race.beep_drop_rpm(Call("box-now", 20, "P1.", "")))
    assert beep.threshold_for(3) == 8500.0


def test_the_ceiling_takes_the_spare_lap_out_of_the_sardegna_fill():
    """Session 177's stop, replayed: 23.1 L aboard in the box, 15 laps left
    after it. Not firm, the fill carries a whole spare lap; at the ceiling it
    carries the measured spread."""
    from pitcrew.race.calls import fuel_target_l

    def in_box(firm: bool) -> RaceState:
        return RaceState(lap=13, laps_total=29, fuel_l=23.06,
                         fuel_per_lap_l=5.519, fuel_sd_l=0.126,
                         fuel_capacity_l=100.0, race_minutes=50.0,
                         laps_estimate_firm=firm, in_pit=True, stint_index=0,
                         stint_ends_on_lap=14, next_stint_laps=15,
                         further_stop_planned=False)

    firm, loose = fuel_target_l(in_box(True)), fuel_target_l(in_box(False))
    assert 83.0 < firm < 85.5            # 15 x 5.519 = 82.8, plus ~1.6 L
    assert loose - firm > 3.5            # the whole lap he told us not to carry
