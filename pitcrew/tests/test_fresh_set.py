"""Whether a run went out on a fresh set, and how the app comes to know.

GT7 broadcasts no tyre-change event, so nothing says outright that a set was
fitted. Two things do say it indirectly, and this module holds both:

* **The driver declares it** on the lap rack, at a run start.
* **The temperatures show it.** GT7 fits every set at one fixed temperature on
  all four corners, so a run that opens there — stationary and even — went out
  on new rubber. Measured from the captures rather than looked up; see
  `thresholds.FRESH_TYRE_TEMP_C`.

Four properties are load-bearing:

* **The control appears exactly where the export starts a run.** A declaration
  made on any other lap would be stored and then ignored.
* **Unset is not "carried over".** `None` and `False` are different claims and
  only one of them is evidence.
* **The driver outranks the stream.** His report is primary; the temperatures
  corroborate it, and where they disagree that disagreement is the finding.
* **The reading says nothing rather than guessing** where it cannot separate a
  fresh set left waiting from a used one left longer.
"""
from __future__ import annotations

from pitcrew.analysis import thresholds
from pitcrew.analysis.runs import fresh_by_temperature, split_runs, starts_run
from pitcrew.analysis.session import LapInput
from pitcrew.analysis.wear import wear_export
from pitcrew.ui.practice_screen import (
    SET_CARRIED,
    SET_FRESH,
    SET_UNDECLARED,
    LapRow,
    RackRow,
    run_start_ids,
)

from .test_controller import qt_app  # noqa: F401
from .test_corners import frame


FITTED = thresholds.FRESH_TYRE_TEMP_C


def a_lap_input(lap_num: int, *, temps=None, speed_kph: float = 0.0,
                **overrides) -> LapInput:
    """One lap, its opening frames stationary at the given corner temps."""
    frames = None
    if temps is not None:
        opening = frame(0.0, speed_kph, 0, temp_fl=temps[0], temp_fr=temps[1],
                        temp_rl=temps[2], temp_rr=temps[3])
        frames = [opening, frame(10.0, 120.0, 1)]
    fields = dict(lap_num=lap_num, lap_time_ms=94_000,
                  fuel_start=round(100.0 - 6.5 * (lap_num - 1), 2),
                  fuel_end=round(100.0 - 6.5 * lap_num, 2),
                  compound="RH", frames=frames)
    fields.update(overrides)
    return LapInput(**fields)


# ------------------------------------------- reading the set off the stream

def test_a_set_as_fitted_reads_the_same_on_all_four_corners():
    """Measured, not looked up: three runs across RS, RM and RH in the 11 Aug
    Monza captures each open at exactly this figure on all four corners."""
    lap = a_lap_input(1, temps=(FITTED, FITTED, FITTED, FITTED))
    assert fresh_by_temperature(lap) is True


def test_a_set_cooled_in_the_box_is_still_recognised():
    """A stationary set only cools, so a fresh one reads at or under the
    fitting temperature. Run 3 of the Monza session opened four degrees down
    after waiting in the garage."""
    cooled = FITTED - 4.0
    assert fresh_by_temperature(
        a_lap_input(1, temps=(cooled, cooled, cooled - 0.1, cooled - 0.1))) is True


def test_corner_to_corner_spread_says_the_set_has_run():
    """The even reading is what does the work, not the absolute value. A set
    picks up asymmetry inside one lap and keeps it."""
    assert fresh_by_temperature(
        a_lap_input(1, temps=(FITTED - 1.7, FITTED - 1.6, FITTED + 0.6,
                              FITTED + 0.8))) is False


def test_a_set_hotter_than_gt7_fits_them_is_not_fresh():
    assert fresh_by_temperature(
        a_lap_input(1, temps=(88.0, 88.0, 88.0, 88.0))) is False


def test_a_set_left_long_enough_to_equalise_cannot_be_told_apart():
    """Null, not false: a fresh set left waiting and a used set left longer
    both end up here, and the reading cannot separate them.

    Measured from the *bottom* of the fitting band, not from the top of it.
    GT7 fits a set anywhere between 60 and 70 C depending on the hour, so a
    reading only becomes unreadable once it has cooled past the coldest
    fitting temperature the game uses.
    """
    cold = thresholds.FRESH_TYRE_TEMP_MIN_C - thresholds.FRESH_TYRE_COOLING_C - 5.0
    assert fresh_by_temperature(
        a_lap_input(1, temps=(cold, cold, cold, cold))) is None


def test_a_set_fitted_on_a_cool_evening_is_still_a_fresh_set():
    """The regression this band was widened for.

    The only real tyre change in the capture set was fitted at 60.0 C on all
    four corners, at 18:50 game time in a session that had opened at 72 C.
    Against a hard 70.0 C the reading came back "cannot tell" for a set that
    had just been bolted on, which is how a fresh set went unnoticed.
    """
    fitted = thresholds.FRESH_TYRE_TEMP_MIN_C
    assert fresh_by_temperature(
        a_lap_input(1, temps=(fitted, fitted, fitted, fitted))) is True


def test_a_car_already_rolling_gives_no_reading():
    """A set already working reads like a used one whether it is or not."""
    assert fresh_by_temperature(
        a_lap_input(1, temps=(FITTED, FITTED, FITTED, FITTED),
                    speed_kph=140.0)) is None


def test_no_frames_means_no_opinion():
    assert fresh_by_temperature(a_lap_input(1)) is None


# ------------------------------------------------------- who outranks whom

def test_the_driver_outranks_the_stream():
    """His report is primary evidence; the stream corroborates it."""
    laps = [a_lap_input(1, temps=(88.0, 88.0, 88.0, 88.0), tyres_fresh=True),
            a_lap_input(2)]
    run = split_runs(laps)[0]
    assert run.tyres_fresh is True
    assert run.tyres_fresh_observed is False
    assert "driver-declared" in run.tyres_fresh_source


def test_a_disagreement_is_surfaced_not_averaged():
    laps = [a_lap_input(1, temps=(88.0, 88.0, 88.0, 88.0), tyres_fresh=True),
            a_lap_input(2)]
    disagreement = split_runs(laps)[0].as_export()["tyresFreshDisagreement"]
    assert "Declared a fresh set" in disagreement
    assert "88.0" in disagreement


def test_the_stream_fills_the_gap_when_he_has_not_said():
    laps = [a_lap_input(1, temps=(FITTED, FITTED, FITTED, FITTED)),
            a_lap_input(2)]
    run = split_runs(laps)[0]
    assert run.tyres_fresh is True
    assert run.tyres_fresh_declared is None
    assert "derived:" in run.tyres_fresh_source


def test_an_agreement_raises_no_finding():
    laps = [a_lap_input(1, temps=(FITTED, FITTED, FITTED, FITTED),
                        tyres_fresh=True),
            a_lap_input(2)]
    assert "tyresFreshDisagreement" not in split_runs(laps)[0].as_export()


def a_lap(lap_id: int, *, tank: float = 100.0, burn: float = 3.4,
          step: int = 0, **overrides) -> LapRow:
    fields = dict(lap_id=lap_id, lap_num=lap_id, lap_time_ms=94_000,
                  fuel_used=burn,
                  fuel_start=round(tank - burn * step, 2),
                  fuel_end=round(tank - burn * (step + 1), 2),
                  session_id=1)
    fields.update(overrides)
    return LapRow(**fields)


def a_run(first_id: int, count: int, **overrides) -> list[LapRow]:
    return [a_lap(first_id + step, step=step, **overrides)
            for step in range(count)]


# ------------------------------------------------- where the control belongs

def test_the_first_lap_of_the_session_can_carry_a_declaration():
    assert run_start_ids(a_run(1, 3)) == {1}


def test_a_refuel_starts_a_run():
    rows = a_run(1, 3) + a_run(4, 2)
    assert run_start_ids(rows) == {1, 4}


def test_going_back_to_the_garage_starts_a_run():
    """A stop and restart means the laps either side are not one stint."""
    rows = a_run(1, 3) + [a_lap(4, step=3, session_id=2)]
    assert run_start_ids(rows) == {1, 4}


def test_coming_in_starts_the_next_run():
    rows = [a_lap(1, step=0), a_lap(2, step=1, is_pit_lap=True),
            a_lap(3, step=2)]
    assert run_start_ids(rows) == {1, 3}


def test_a_lap_mid_tank_carries_no_declaration():
    """One question per run, not one per lap, on a screen he visits between
    runs."""
    assert 2 not in run_start_ids(a_run(1, 4))


def test_a_declaration_already_made_keeps_its_control():
    """Hiding it would hide something he said that is still stored."""
    rows = a_run(1, 3)
    rows[1].tyres_fresh = True
    assert run_start_ids(rows) == {1, 2}


def test_the_rack_and_the_export_agree_on_where_a_run_starts():
    """The property that makes the control worth having: a declaration made
    on the rack must land on a lap the export treats as a run start."""
    rows = a_run(1, 3) + a_run(4, 4) + a_run(8, 2)
    laps = [LapInput(lap_num=row.lap_num, lap_time_ms=row.lap_time_ms,
                     fuel_start=row.fuel_start, fuel_end=row.fuel_end,
                     is_pit_lap=row.is_pit_lap, session_id=row.session_id)
            for row in rows]
    assert {run.first_lap for run in split_runs(laps)} == run_start_ids(rows)


def test_the_boundary_rule_is_shared_not_reimplemented():
    first, second = a_run(1, 2)
    assert starts_run(first, second) is False
    assert starts_run(second, a_lap(3, step=0)) is True


# ------------------------------------------------------------- the control

def test_only_a_run_start_row_is_given_the_picker(qt_app):  # noqa: F811
    plain = RackRow(a_lap(2, step=1), 94_000, run_start=False)
    starting = RackRow(a_lap(1), 94_000, run_start=True)
    assert plain.set_picker is None
    assert starting.set_picker is not None


def test_the_picker_offers_three_states_and_starts_unsaid(qt_app):  # noqa: F811
    widget = RackRow(a_lap(1), 94_000, run_start=True)
    picker = widget.set_picker
    assert [picker.itemText(i) for i in range(picker.count())] == [
        SET_UNDECLARED, SET_FRESH, SET_CARRIED]
    assert picker.currentData() is None


def test_declaring_a_fresh_set_reaches_the_row(qt_app):  # noqa: F811
    row = a_lap(1)
    widget = RackRow(row, 94_000, run_start=True)
    seen = []
    widget.changed.connect(seen.append)
    widget.set_picker.setCurrentText(SET_FRESH)
    assert row.tyres_fresh is True
    assert seen == [1]


def test_carried_over_is_false_and_unsaid_is_none(qt_app):  # noqa: F811
    """Two different claims, and only one of them is evidence."""
    row = a_lap(1)
    widget = RackRow(row, 94_000, run_start=True)
    widget.set_picker.setCurrentText(SET_CARRIED)
    assert row.tyres_fresh is False
    widget.set_picker.setCurrentText(SET_UNDECLARED)
    assert row.tyres_fresh is None


def test_an_existing_declaration_is_shown_not_reset(qt_app):  # noqa: F811
    widget = RackRow(a_lap(1, tyres_fresh=True), 94_000, run_start=True)
    assert widget.set_picker.currentData() is True


def test_loading_a_declaration_does_not_look_like_an_edit(qt_app):  # noqa: F811
    """Rebuilding the rack must not fire a save."""
    widget = RackRow(a_lap(1, tyres_fresh=False), 94_000, run_start=True)
    seen = []
    widget.changed.connect(seen.append)
    assert widget.set_picker.currentData() is False
    assert seen == []


# ----------------------------------------------------- what it buys the model

def test_declaring_the_set_fresh_makes_the_rate_measured():
    laps = [LapInput(lap_num=n, lap_time_ms=94_000,
                     fuel_start=round(100.0 - 6.5 * (n - 1), 2),
                     fuel_end=round(100.0 - 6.5 * n, 2), compound="RH",
                     wear_rl=0.42 if n == 6 else None,
                     tyres_fresh=True if n == 1 else None)
            for n in range(1, 7)]
    wear = wear_export(laps)
    assert wear["byRun"][0]["confidence"] == "measured"
    assert wear["modelConfidence"] == "measured"
    assert "assumesFreshAtLap" not in wear["byRun"][0]


def test_saying_the_set_carried_over_does_not_make_it_measured():
    """It is evidence, but it is evidence *against* the rate being knowable:
    the set had unknown life on it when the run began."""
    laps = [LapInput(lap_num=n, lap_time_ms=94_000,
                     fuel_start=round(100.0 - 6.5 * (n - 1), 2),
                     fuel_end=round(100.0 - 6.5 * n, 2), compound="RH",
                     wear_rl=0.42 if n == 6 else None,
                     tyres_fresh=False if n == 1 else None)
            for n in range(1, 7)]
    record = wear_export(laps)["byRun"][0]
    assert record["confidence"] == "assumed"
    assert record["assumesFreshAtLap"] == 1
