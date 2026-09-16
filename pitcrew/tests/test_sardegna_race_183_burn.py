"""Sardegna, session 183: 29 laps of fuel calls sized on the practice burn.

RSR at Sardegna Road Track A, 16 Sep 2026, strategy 36 - RM 12 then RH 17,
**both stints declared `fuel_save`**. At 13:04:00 the engineer said:

    "Fuel to 97 litres. 17 laps after the box, at the practice burn."

17 laps at the burn the race was actually showing on the beep (5.365 L/lap)
is 91.2 L. 97 is about six litres more, and at the measured 1.00 L/s that is
six seconds standing at the pump. The same 97 L was said in session 179 the
night before, from the same cause.

**The cause was a filter that could never be satisfied.** `note_lap` dropped
every lap carrying `short_shift_rpm` on the sound reasoning that a lap driven
under a one-off short-shift instruction is evidence about the instruction and
not about the car. But since the 15 Sep `fuel_save` plan field a whole stint
can hand the beep over, and then the stamp is set on EVERY lap - 500.0 on all
29 of this race. So `green_laps()` never reached `BURN_LAPS_NEEDED`, the burn
was never installed, and `state.fuel_per_lap_l` held `build_inputs`' practice
figure to the flag. CLAUDE.md rule 10: a refusal that can never be cleared,
and silent - "burn installed on lap N" appears zero times in the log for this
session, and the only clue anywhere was those four spoken words.

**Two things had to be told apart, and `short_shift_rpm` can tell neither.**

* Which column he actually drove. The stamp says the beep was on its saving
  points; it does not say he obeyed it. On laps 27-29 he drove full revs off
  his own fuel readout while the beep sat on the saving column - upshifts at
  8421/8442/8378 rpm against ~7380 before, and 7.04 L/lap against 5.37. What
  he actually did is `upshift_rpm`, measured off the frames, exactly as
  `analysis/driving.py`'s own header says.
* Which column the burn belongs to. Pooling this race's 29 laps gives about
  5.6 L/lap - within a rounding error of the practice 5.586 that caused the
  bug, so a fix that pools would size the fill at 97 L again and look right.

Every figure below is read off `data/pitcrew.db` session 183 and strategy 36;
the issued table is `shift_points` id 1 (performance 8500, saving 7400 in
gears 1-5), whose midpoint is what sorts the two columns.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer.shift_points import ShiftPoints
from pitcrew.race.calls import fuel_target_l
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.race.expectations import (
    FUEL_BASIS_COLUMN,
    FUEL_BASIS_COLUMN_HIGHER,
)
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent


# The practice figure the plan was costed with and the race then ran on.
PRACTICE_BURN = 5.586

# `lap_num: (lap_time_ms, fuel_start, fuel_end, fuel_used, pit, out,
#            upshift_rpm, position)` - session 183's `laps` rows, verbatim.
LAPS = {
    1: (106509, 100.000, 94.563, 5.437, 0, 0, 7367.0, 10),
    2: (102742, 94.563, 89.237, 5.325, 0, 0, 7383.0, 8),
    3: (102675, 89.237, 83.816, 5.421, 0, 0, 7439.0, 5),
    4: (102074, 83.816, 78.403, 5.413, 0, 0, 7406.0, 3),
    5: (102838, 78.403, 72.968, 5.435, 0, 0, 7406.0, 2),
    6: (102422, 72.968, 67.539, 5.430, 0, 0, 7410.0, 1),
    7: (102666, 67.539, 62.027, 5.512, 0, 0, 7388.0, 1),
    8: (102645, 62.027, 56.574, 5.453, 0, 0, 7384.0, 1),
    9: (102845, 56.574, 51.234, 5.340, 0, 0, 7367.0, 1),
    10: (103384, 51.234, 45.914, 5.320, 0, 0, 7369.0, 1),
    11: (102846, 45.914, 40.518, 5.396, 0, 0, 7381.0, 1),
    12: (184773, 40.518, 96.502, 5.136, 1, 0, 7382.0, 20),
    13: (106514, 96.502, 91.333, 5.169, 0, 1, 7355.0, 20),
    14: (104725, 91.333, 85.917, 5.416, 0, 0, 7405.0, 20),
    15: (103464, 85.917, 80.550, 5.366, 0, 0, 7366.0, 16),
    16: (104967, 80.550, 75.220, 5.330, 0, 0, 7389.0, 1),
    17: (103542, 75.220, 69.849, 5.371, 0, 0, 7374.0, 1),
    18: (104911, 69.849, 64.551, 5.298, 0, 0, 7364.0, 1),
    19: (104003, 64.551, 59.183, 5.369, 0, 0, 7391.0, 1),
    20: (106672, 59.183, 53.894, 5.288, 0, 0, 7400.0, 1),
    21: (103458, 53.894, 48.522, 5.372, 0, 0, 7392.0, 1),
    22: (104395, 48.522, 43.265, 5.257, 0, 0, 7391.0, 1),
    23: (102973, 43.265, 37.859, 5.406, 0, 0, 7368.0, 1),
    24: (103349, 37.859, 32.494, 5.365, 0, 0, 7377.0, 1),
    25: (114268, 32.494, 27.098, 5.396, 0, 0, 7430.0, 3),
    26: (104583, 27.098, 21.662, 5.435, 0, 0, 7399.0, 2),
    # He went to full revs here, off his own fuel readout. The beep did not
    # move and `short_shift_rpm` stayed at 500.0 on all three.
    27: (105519, 21.662, 14.628, 7.035, 0, 0, 8421.0, 2),
    28: (102782, 14.628, 7.585, 7.043, 0, 0, 8442.0, 1),
    29: (103256, 7.585, 1.068, 6.517, 0, 0, 8378.0, 1),
}

# Strategy 36, as approved. Both stints on the saving column.
PLAN = {
    "stops": 1, "pit_laps": [12], "laps": 29, "max_race_laps": 29,
    "binding_constraint": "tyre",
    "fuel_burns": {"save": 5.33, "full": 6.86},
    "stints": [
        {"laps": 12, "compound": "RM", "fuel_l": 100.0, "start_lap": 1,
         "fuel_save": True},
        {"laps": 17, "compound": "RH", "fuel_l": 95.0, "start_lap": 13,
         "tyres": True, "fuel_save": True},
    ],
}

# `shift_points` id 1: the box in the car, measured on this circuit.
ISSUED = ShiftPoints(
    car_name="Porsche 911 RSR (991) '17",
    circuit_key="sardegna-road-track-layout-a",
    performance={g: 8500.0 for g in range(1, 6)},
    fuel_saving={g: 7400.0 for g in range(1, 6)})


class _Driven:
    """`analysis.driving.DrivingRead`, as much of it as the race reads."""

    def __init__(self, upshift_rpm: float) -> None:
        self.coast_pct = 3.0
        self.full_throttle_pct = 55.0
        self.upshift_rpm = upshift_rpm
        self.upshifts = 40
        self.frames = 6200
        self.braking_pct = 14.0


def lap_event(lap_num: int) -> SessionEvent:
    ms, start, end, used, pit, out, _rpm, position = LAPS[lap_num]
    lap = Lap(
        lap_num=lap_num, lap_time_ms=ms, best_lap_ms=102_074,
        delta_ms=ms - 102_074, fuel_start=start, fuel_end=end,
        fuel_used=used, position=position,
        is_pit_lap=bool(pit), is_out_lap=bool(out),
        # **The stamp that caused all of this**, on every lap of the race,
        # because the plan hands the beep to George for both stints.
        short_shift_rpm=500.0)
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": lap})


def a_race(*, issue_the_table: bool = True) -> RaceCoordinator:
    race = RaceCoordinator(
        PLAN,
        fuel_per_lap_l=PRACTICE_BURN,
        fuel_capacity_l=100.0,
        lap_time_ms=102_300,
        practice_lap_samples=9, practice_fuel_samples=9)
    assert race.arm(None, PlanContext(
        car="Porsche 911 RSR (991) '17", track="Sardegna Road Track",
        layout="Layout A", race_laps=29)) is True
    if issue_the_table:
        race.note_shift_columns(ISSUED)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 29}))
    return race


def drive(race: RaceCoordinator, through: int) -> None:
    """Laps 1..`through`, wired the way the controller wires them.

    The driving read is handed over before the crossing because that is the
    order the two Qt signals are emitted in - `lap_completed` then
    `session_event`. `test_the_column_is_corrected_when_the_read_lands_late`
    drives the other order.
    """
    for lap_num in range(1, through + 1):
        race.note_driving(lap_num, _Driven(LAPS[lap_num][6]))
        race.handle(lap_event(lap_num))


# ------------------------------------------------- the burn actually installs

def test_the_race_burn_installs_on_the_fifth_green_lap(caplog):
    """"burn installed on lap N" appeared ZERO times in the real run.

    **Lap 6, not lap 5**: `BURN_LAPS_NEEDED` counts green laps and lap one of
    a standing start is not one - it carries the grid and the launch and is
    slower and thirstier by construction. So laps 2-6 are the five.
    """
    import logging

    caplog.set_level(logging.INFO, logger="pitcrew.race")
    race = a_race()
    drive(race, 5)
    assert race.state.fuel_burn_basis is None, "four green laps is not five"
    race.note_driving(6, _Driven(LAPS[6][6]))
    race.handle(lap_event(6))
    installed = [r.getMessage() for r in caplog.records
                 if "burn installed" in r.getMessage()]
    assert installed, "the race ran to the flag on practice and said nothing"
    assert "burn installed on lap 6" in installed[0]
    assert race.state.fuel_burn_basis is not None
    assert race.state.fuel_burn_why is None


def test_the_installed_burn_is_the_saving_column_and_not_practice():
    """5.35-5.45, which is what laps 2-11 burned. **Not ~5.6**: that is what
    pooling this race's two columns gives, and it is within a rounding error
    of the practice 5.586 that caused the bug."""
    race = a_race()
    drive(race, 11)
    assert race.state.fuel_per_lap_l == pytest.approx(5.40, abs=0.05)
    assert race.state.fuel_per_lap_l != PRACTICE_BURN


def test_the_fill_at_the_stop_is_sized_on_this_races_burn():
    """The real call was 97 L. 17 laps on the beep wants 91-93."""
    race = a_race()
    drive(race, 11)
    litres = fuel_target_l(race.state)
    assert litres is not None
    assert 91.0 <= litres <= 93.0, f"the fill came out at {litres:.1f} L"


def test_the_fill_on_the_old_practice_burn_is_the_97_litres_he_heard():
    """The bug, pinned: the same stop sized on `PRACTICE_BURN` is the figure
    that was actually spoken. Without this the test above could pass on a
    coincidence of margins."""
    race = a_race()
    drive(race, 11)
    race.state.fuel_per_lap_l = PRACTICE_BURN
    race.state.fuel_reference_load_l = None
    race.state.fuel_sd_l = None
    litres = fuel_target_l(race.state)
    assert litres is not None and round(litres) >= 96


# --------------------------------------------- and the columns stay apart

def test_full_revs_laps_do_not_drag_the_saving_burn_up():
    """Laps 27-29 burned 7.04, 7.04 and 6.52 on a column the other 23 laps
    were not driven on. A pooled median would carry them."""
    race = a_race()
    drive(race, 29)
    saving = race.expect.race_fuel_per_lap_l(True)
    full = race.expect.race_fuel_per_lap_l(False)
    assert saving == pytest.approx(5.37, abs=0.06)
    assert full == pytest.approx(6.87, abs=0.30)
    assert race.expect.race_burn_laps(False) == 3


def test_the_column_he_drove_is_read_off_the_frames_not_off_the_stamp():
    """`short_shift_rpm` is 500.0 on all three of laps 27-29. The upshift rpm
    is 8421/8442/8378 against an issued midpoint of 7950."""
    race = a_race()
    drive(race, 29)
    assert race._column_rpm == 7950.0
    assert race._measured_column(26) is True
    assert race._measured_column(27) is False
    assert race.state.fuel_save_engaged is True, \
        "the beep never moved - only the driver did"


def test_the_switch_to_full_revs_is_priced_and_not_left_stale():
    """Three laps is under `BURN_LAPS_NEEDED`, so the column he moved to has
    no burn of its own to the precision the fill needs. Holding 5.37 while he
    burns 7.0 is a confident wrong answer, and so is a conversion that comes
    out under what he is visibly burning - the higher of the two wins and
    names itself."""
    race = a_race()
    drive(race, 29)
    assert race.state.fuel_burn_basis == FUEL_BASIS_COLUMN_HIGHER
    # The plan's ratio converts 23 saving laps to 6.91; his own three full
    # laps say 7.04. The higher of the two, because light is the direction
    # that says "fuel good" about a tank that is short.
    assert race.state.fuel_per_lap_l == pytest.approx(7.04, abs=0.05)
    # Too few of this column's own laps to anchor a load to (rule 3).
    assert race.state.fuel_reference_load_l is None


def test_the_burn_moves_to_the_new_column_on_the_crossing_it_changes():
    """**Not a lap later.** The populations are keyed on the column, and a
    column is otherwise only learned when a lap driven on it completes - so
    the first full-revs lap would be fuelled at the saving rate, 30% light."""
    race = a_race()
    drive(race, 26)
    assert race.state.fuel_per_lap_l == pytest.approx(5.37, abs=0.06)
    # George moves the beep at this crossing, as he does when the fuel says
    # there is enough for full revs to the flag.
    race.expect.set_column(False)
    burn, laps, basis = race.expect.current_fuel_basis()
    assert basis == FUEL_BASIS_COLUMN
    assert burn == pytest.approx(6.91, abs=0.1)
    assert laps >= 5, "priced off the other column's laps, not off nothing"


def test_the_column_is_corrected_when_the_read_lands_late():
    """The two signals arrive in order in production, but a lap whose frames
    were short carries no read at all - so the correction must work from
    either side of the crossing."""
    race = a_race()
    for lap_num in range(1, 30):
        race.handle(lap_event(lap_num))
        race.note_driving(lap_num, _Driven(LAPS[lap_num][6]))
    assert race.expect.race_fuel_per_lap_l(True) == pytest.approx(5.37,
                                                                  abs=0.06)
    assert race.expect.race_burn_laps(False) == 3


# ------------------------------------------------------- and it says so

def test_with_no_issued_table_the_refusal_is_spoken_once_not_swallowed():
    """No table means the columns cannot be told apart off the frames, and
    the classifier falls back to the app's own switch. Whatever it then
    decides, a race running on practice must SAY so - the whole reason this
    took a race and a half to find is that nothing did."""
    race = a_race(issue_the_table=False)
    for lap_num in range(1, 30):
        race.handle(lap_event(lap_num))
    assert race._column_rpm is None
    if race.state.fuel_burn_basis is None:
        assert race.state.fuel_burn_why
        assert "practice burn" in race.state.fuel_burn_why


def test_a_race_with_no_fuel_save_plan_is_left_exactly_as_it_was():
    """One column, and a lap under a one-off short-shift instruction is still
    evidence about the instruction. Nothing above may reach a race the plan
    does not hand the beep for."""
    plan = {**PLAN, "stints": [
        {"laps": 12, "compound": "RM", "fuel_l": 100.0, "start_lap": 1},
        {"laps": 17, "compound": "RH", "fuel_l": 95.0, "start_lap": 13,
         "tyres": True},
    ]}
    race = RaceCoordinator(plan, fuel_per_lap_l=PRACTICE_BURN,
                           fuel_capacity_l=100.0, lap_time_ms=102_300)
    assert race.arm(None, PlanContext(
        car="Porsche 911 RSR (991) '17", track="Sardegna Road Track",
        layout="Layout A", race_laps=29)) is True
    race.note_shift_columns(ISSUED)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 29}))
    assert race.state.fuel_save_engaged is None
    drive(race, 11)
    # Every lap carries the stamp, so every lap is an instructed lap and the
    # population is empty - exactly as it was before any of this.
    assert race.expect.green_laps() == 0
    assert race.state.fuel_per_lap_l == PRACTICE_BURN
