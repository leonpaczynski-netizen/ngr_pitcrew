"""Qualifying and race running are different measurements of the same laps.

*"I want to load both race and quali car setups into the app and have them
appear in different sections of the app. Quali practice and race practice both
of which look at completely different things."*

They do. A qualifying run is one lap on low fuel and fresh rubber, where
degradation across the session is noise. Race running is the opposite: the
single fastest lap is the noise and the shape of the stint is the measurement.
Reporting both the same way is how a one-lap car gets built for a race.

Intent is orthogonal to where the car started — a qualifying simulation is
usually a time trial and race running is usually a lobby, but neither is
implied by the other, so they are asked separately.
"""
from __future__ import annotations



from pitcrew.analysis.runs import FOR_QUALIFYING, FOR_RACE, LOBBY, TIME_TRIAL
from pitcrew.setup.sheet import SetupSheet
from pitcrew.store.db import Store
from pitcrew.ui.practice_screen import LapRow, PracticeScreen

from .test_controller import qt_app  # noqa: F401


def a_lap(num: int, ms: int, **overrides) -> LapRow:
    fields = dict(lap_id=num, lap_num=num, lap_time_ms=ms, fuel_used=6.0,
                  fuel_start=100.0 - 6.0 * (num - 1),
                  fuel_end=100.0 - 6.0 * num, compound="RM", session_id=1)
    fields.update(overrides)
    return LapRow(**fields)


# ------------------------------------------------------------- what it shows

def test_race_running_reports_the_stint(qt_app):
    screen = PracticeScreen()
    screen.set_practice_intent(FOR_RACE)
    screen.set_laps([a_lap(n, 109_000 + n * 200) for n in range(1, 8)])
    assert screen.practice_intent() == FOR_RACE
    # Median and fuel per lap describe a stint; they are what race running is.
    labels = _labels(screen)
    assert any("Median" in label for label in labels)
    assert any("Fuel" in label for label in labels)


def test_qualifying_reports_the_one_lap(qt_app):
    """A median over a qualifying run describes laps he was not trying to set
    a time on, and fuel per lap describes nothing at all."""
    screen = PracticeScreen()
    screen.set_practice_intent(FOR_QUALIFYING)
    screen.set_laps([a_lap(n, 109_000 + n * 200) for n in range(1, 8)])
    labels = _labels(screen)
    assert "Median" not in " ".join(labels)
    assert any("2nd best" in label for label in labels)
    assert any("Spread" in label for label in labels)
    assert any("On" == label for label in labels)   # the fuel it was set on


def _labels(screen) -> list[str]:
    return [label.text() for label, _ in screen.spec._entries]


# ------------------------------------------------------- which sheet is fitted

def test_a_car_can_hold_a_race_sheet_and_a_qualifying_sheet(store: Store):
    race = SetupSheet(car_name="RSR", sheet_name="Monza race",
                      values={"rh_f": 60}, purpose="race")
    quali = SetupSheet(car_name="RSR", sheet_name="Monza quali",
                       values={"rh_f": 55}, purpose="qualifying")
    store.save_setup_sheet(race)
    store.save_setup_sheet(quali)

    assert store.sheet_for("RSR", "race").sheet_name == "Monza race"
    assert store.sheet_for("RSR", "qualifying").sheet_name == "Monza quali"


def test_an_unlabelled_sheet_counts_as_a_race_sheet_and_never_as_quali(store: Store):
    """Every sheet stored before the question was asked was a race sheet. A
    qualifying sheet that was never labelled has to be labelled, not guessed."""
    store.save_setup_sheet(SetupSheet(car_name="RSR", sheet_name="v1",
                                      values={"rh_f": 60}))
    assert store.sheet_for("RSR", "race").sheet_name == "v1"
    assert store.sheet_for("RSR", "qualifying") is None


def test_the_purpose_travels_into_the_export(store: Store):
    sheet = SetupSheet(car_name="RSR", sheet_name="q", values={"rh_f": 55},
                       purpose="qualifying")
    assert sheet.as_export()["purpose"] == "qualifying"


def test_a_sheet_that_has_not_said_omits_it_rather_than_guessing(store: Store):
    sheet = SetupSheet(car_name="RSR", sheet_name="v1", values={"rh_f": 60})
    assert "purpose" not in sheet.as_export()


# -------------------------------------------------------------- the rehearsal

def test_a_rehearsal_is_a_race_session_that_is_not_the_race(store: Store, event_id):
    """It makes real stops under race conditions, which is the only place that
    evidence comes from — and it is not the league race."""
    session_id = store.start_session(event_id, "race", rehearsal=True)
    session = store.get_session(session_id)
    assert session["kind"] == "race"
    assert session["rehearsal"] == 1


def test_an_ordinary_race_is_not_flagged_as_one(store: Store, event_id):
    session_id = store.start_session(event_id, "race")
    assert store.get_session(session_id)["rehearsal"] == 0


# ------------------------------------------------------------- the two axes

def test_intent_and_mode_are_recorded_separately(store: Store, event_id):
    """Neither implies the other: a qualifying simulation in a lobby and race
    running in a time trial are both things he does."""
    session_id = store.start_session(
        event_id, "practice", practice_mode=LOBBY,
        practice_intent=FOR_QUALIFYING)
    session = store.get_session(session_id)
    assert (session["practice_mode"], session["practice_intent"]) == (
        LOBBY, FOR_QUALIFYING)

    other = store.start_session(
        event_id, "practice", practice_mode=TIME_TRIAL,
        practice_intent=FOR_RACE)
    session = store.get_session(other)
    assert (session["practice_mode"], session["practice_intent"]) == (
        TIME_TRIAL, FOR_RACE)


def test_both_are_correctable_after_the_fact(store: Store, event_id):
    """Asked immediately before going out, which is the worst moment to make
    anybody answer a question carefully."""
    session_id = store.start_session(event_id, "practice",
                                     practice_intent=FOR_RACE)
    store.set_practice_intent(session_id, FOR_QUALIFYING)
    store.set_practice_mode(session_id, TIME_TRIAL)
    session = store.get_session(session_id)
    assert session["practice_intent"] == FOR_QUALIFYING
    assert session["practice_mode"] == TIME_TRIAL


# ------------------------------------------------------ keeping his place

def test_marking_a_lap_does_not_throw_him_back_to_the_top(qt_app):
    """*"when I select a tyre compound or strike through a lap in practice it
    takes me to the top of the page"*

    Both go through `_rebuild_rack`, which destroys every row widget and
    builds it again - so the scroll area's contents momentarily have no height
    and the bar clamps to zero. On a long session that is once per mark, and
    the marking up is the whole point of the screen.
    """
    screen = PracticeScreen()
    screen.set_laps([a_lap(n, 109_000 + n * 137) for n in range(1, 41)])
    screen.resize(1400, 600)
    screen.show()
    qt_app.processEvents()

    bar = screen.scroller.verticalScrollBar()
    assert bar.maximum() > 0, "forty laps should not fit in six hundred pixels"
    bar.setValue(bar.maximum() // 2)
    qt_app.processEvents()
    was = bar.value()

    screen._rows[19].excluded = True
    screen._rebuild_rack()
    # Several turns, because the rack genuinely has no height for one of them:
    # the old rows are destroyed on the first, so the layout collapses before
    # the new ones are measured. That collapse is why a `singleShot(0)` cannot
    # do this job.
    for _ in range(5):
        qt_app.processEvents()

    assert bar.maximum() > 0
    assert abs(bar.value() - was) < bar.maximum() * 0.05, (
        f"struck a lap at {was} and landed at {bar.value()}")
    screen.hide()
