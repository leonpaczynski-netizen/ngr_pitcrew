"""The event screen, fed from the league calendar.

Two things are under test here and they fail in different directions. The
**series** half is a regression: the Event screen has always sent a league name
and the controller always dropped it, so every event on file reads NULL. The
**calendar** half is new behaviour: the app opens on the round that is coming
rather than on whichever event was last active, and a round the hub has not
fully described is never written down as though it had been.
"""
from __future__ import annotations

import datetime
import json
import sqlite3

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from pitcrew.controller import PitCrewController          # noqa: E402
from pitcrew.hub import read as hub_read                   # noqa: E402
from pitcrew.store.db import Store                         # noqa: E402
from pitcrew.ui.event_screen import (                      # noqa: E402
    HUB_HEADING,
    NEW_EVENT,
    EventScreen,
)
from pitcrew.ui.practice_screen import PracticeScreen      # noqa: E402

from .test_hub_calendar import GR3, SCHEMA                 # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app

# A bare circuit name, which the hub's format defines as its base layout.
COMPLETE = "Michelin Raceway Road Atlanta"
# A circuit the app knows at a layout it does not: the hub's Nurburgring
# "Endurance II" has no catalogue entry here. **This is what incomplete looks
# like now.** It used to be any circuit the hub named without a layout, which
# was a misreading - a bare name is a statement that the round runs the base
# configuration, not the hub declining to say.
INCOMPLETE = "N\u00fcrburgring \u2014 Endurance II"

# **Relative to the day the test runs, not to the day it was written.**
# These were two fixed dates in September 2026; the first of them went past
# and eleven tests failed on a calendar rather than on a change. What the
# fixtures mean is "the next round" and "the one after", so that is what they
# say - a week out and a fortnight out, on the same 10:30 UTC the league
# runs.
def _round_at(days: int) -> str:
    when = (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=days)).replace(
        hour=10, minute=30, second=0, microsecond=0)
    return when.strftime("%Y-%m-%dT%H:%M:%S.000+00:00")


SOON = _round_at(7)
LATER = _round_at(14)


@pytest.fixture()
def hub_at(tmp_path, monkeypatch):
    """Build a hub and make it the one the controller opens."""
    def build(rounds, *, cars=()):
        path = tmp_path / "league.db"
        db = sqlite3.connect(path)
        db.executescript(SCHEMA)
        db.execute(
            "INSERT INTO Series (id, name, status, defaultLobbySettings) "
            "VALUES ('s1', 'NGR GR3', 'ACTIVE', ?)", (json.dumps(GR3),))
        db.execute(
            "INSERT INTO Driver VALUES ('d1', 'u1', 'Beeni', 'Beeni-187')")
        db.execute("INSERT INTO SeriesRegistration VALUES "
                   "('sr1', 's1', 'd1', 'Lamborghini Huracan GT3', 'OK')")
        for rid, when, track in rounds:
            db.execute("INSERT INTO Round VALUES "
                       "(?, 's1', ?, ?, 'SCHEDULED', 1, ?, 'null')",
                       (rid, rid, when, track))
        for n, (rid, car, bhp, kg) in enumerate(cars):
            db.execute(
                "INSERT INTO RoundCarOverride VALUES (?, ?, ?, NULL, ?, ?)",
                (f"co{n}", rid, car, bhp, kg))
        db.commit()
        db.close()
        monkeypatch.setattr(hub_read, "DEFAULT_PATH", path)
        return path
    return build


@pytest.fixture()
def wired(qt_app, store: Store):
    # **The name is what the whole calendar hangs off.** Without it `upcoming`
    # cannot narrow to his leagues or find his car, which is exactly the state
    # the real app was in - `driver_name` was never set, so the league line and
    # the pit wall both went dark for want of one setting.
    store.set_driver_name("Beeni")
    event_screen = EventScreen()
    practice = PracticeScreen()
    controller = PitCrewController(store, event_screen, practice)
    yield controller, event_screen, practice, store
    controller.shutdown()


def an_event(**overrides) -> dict:
    data = {
        "name": "Round 4 - Fuji", "track": "Fuji Speedway", "layout": "Full",
        "car_name": "Porsche 911 RSR (991) '17", "race_type": "laps",
        "race_laps": 20, "weather": "dry", "tyre_wear_mult": "4x",
        "fuel_mult": "2x", "refuel_rate_lps": 2.5, "pit_loss_secs": 20.0,
        "mandatory_stops": 0, "abs_setting": "Weak", "tcs": 1,
        "available_compounds": ["RH", "RM", "RS"],
        "setup_values": {}, "sheet_name": "", "gear_text": "",
    }
    data.update(overrides)
    return data


# --- the series, which was being dropped ------------------------------------

def test_the_league_typed_on_the_event_is_actually_stored(wired):
    """**A straight regression.** The Event screen has had a Series box since
    it was built, `events.series` has existed since schema v13, and every event
    on file still reads NULL: `values()` sent the name and `_on_event_saved`
    never copied it into the write. Two things depended on it and both failed
    quietly - the hub could only match a league by guessing from the car, and
    the box's own completer fed from a column that was always empty."""
    controller, _, _, store = wired
    controller._on_event_saved(an_event(series="NGR GR3"))
    assert store.get_event(store.active_event_id())["series"] == "NGR GR3"


def test_a_league_is_not_invented_for_an_event_that_names_none(wired):
    """Null rather than empty string: an unlabelled event is one from before
    there was more than one league, not a league called nothing.

    Paired with the test above so the two together pin the copy: this one alone
    would pass with `series` dropped from `_on_event_saved` entirely, because
    the column defaults to NULL."""
    controller, _, _, store = wired
    controller._on_event_saved(an_event(series=None))
    assert store.get_event(store.active_event_id())["series"] is None


def test_renaming_a_league_on_an_event_replaces_it_rather_than_adding_one(
        wired):
    """The copy has to survive an update as well as a create - `update_event`
    writes only the keys it is handed, so a `series` missing from the second
    save would leave the first name standing and read as unchanged."""
    controller, _, _, store = wired
    controller._on_event_saved(an_event(series="NGR GR3"))
    event_id = store.active_event_id()
    controller._on_event_saved(an_event(id=event_id, series="NGR Supercars"))
    assert store.get_event(event_id)["series"] == "NGR Supercars"


def test_what_the_form_cannot_edit_survives_the_save_that_creates_the_event(
        wired, hub_at):
    """**The create is the path that loses them, and the only one.**
    `update_event` writes only the keys it is handed, so an existing row keeps
    a column nobody sent; `create_event` fills every absent column from the
    schema, where `required_compounds` becomes `[]` - indistinguishable from
    "the league requires no particular compound" - and `hub_round_id` becomes
    NULL, which puts the round back on the calendar as though it had never
    been recorded.

    So this drives the incomplete-round path: the form is filled from a
    proposal, `_event_id` is None, and Save is a create."""
    hub_at((("r1", SOON, INCOMPLETE),))
    controller, event_screen, _, store = wired
    controller.switch_event("r1")             # fills the form, stores nothing
    assert store.active_event_id() is None

    values = event_screen.values()
    assert values["hub_round_id"] == "r1"
    assert values["required_compounds"] == ["RS", "RM"]

    controller._on_event_saved({**an_event(), **values,
                                "layout": "Endurance"})

    saved = store.get_event(store.active_event_id())
    assert saved["hub_round_id"] == "r1"
    assert saved["required_compounds"] == ["RS", "RM"]


# --- opening on the next round ----------------------------------------------

def test_the_app_opens_on_the_round_that_is_coming(wired, hub_at):
    """Not on whichever event was last active, which after a debrief is the one
    just finished."""
    hub_at((("r1", SOON, COMPLETE),))
    controller, _, _, store = wired
    controller._on_event_saved(an_event(name="Last week"))
    stale = store.active_event_id()

    controller.open_on_next_round()

    opened = store.get_event(store.active_event_id())
    assert opened["id"] != stale
    assert opened["hub_round_id"] == "r1"
    assert opened["track"] == COMPLETE


def test_the_regulations_come_off_the_hub_and_not_off_memory(wired, hub_at):
    """The stored Daytona event says `mandatory_stops = 0` on a round the
    league publishes as a mandatory one-stop, and that figure is an input to
    the strategy engine."""
    hub_at((("r1", SOON, COMPLETE),),
           cars=(("r1", "Lamborghini Huracan GT3", 550, 1275),))
    controller, _, _, store = wired
    controller.open_on_next_round()

    event = store.get_event(store.active_event_id())
    assert event["mandatory_stops"] == 1
    assert event["tyre_wear_mult"] == "2x"
    assert event["fuel_mult"] == "3x"
    assert event["available_compounds"] == ["RS", "RM", "RH"]
    assert event["series"] == "NGR GR3"
    assert event["car_name"] == "Lamborghini Huracan GT3"


def test_the_refuel_rate_reaches_the_event_and_says_it_came_from_the_hub(
        wired, hub_at):
    """`refuelRate` is litres per second - the app's own Daytona measurement of
    1.003 L/s corroborates the league's 1.

    **The source is the half that matters.** `refuel_rate_lps` is NOT NULL with
    a default of 2.5, so without a provenance beside it a league figure and the
    schema's placeholder are the same number to every reader downstream."""
    hub_at((("r1", SOON, COMPLETE),))
    controller, _, _, store = wired
    controller.open_on_next_round()

    event = store.get_event(store.active_event_id())
    assert event["refuel_rate_lps"] == 1.0
    assert event["refuel_rate_source"] == "hub"


def test_the_game_clock_can_still_be_measured_on_a_hub_event(wired, hub_at):
    """**A latch, and rule 10 names this shape.** `record_measured_clock`
    refuses to overwrite a multiplier already set unless `clock_source` says
    `measured`. Writing the hub's `variableTimeSpeedRate` set the value without
    the source, so the event refused every measurement it was ever offered and
    `start_hour` stayed NULL for ever."""
    hub_at((("r1", SOON, COMPLETE),))
    controller, _, _, store = wired
    controller.open_on_next_round()
    event_id = store.active_event_id()

    assert store.get_event(event_id)["time_multiplier"] is None
    assert store.record_measured_clock(event_id, 14.5, 2.0) is True


def test_opening_twice_does_not_create_the_round_twice(wired, hub_at):
    """A round already recorded is switched to, not created again - otherwise
    every launch forks it and the laps split between the halves."""
    hub_at((("r1", SOON, COMPLETE),))
    controller, _, _, store = wired
    controller.open_on_next_round()
    first = store.active_event_id()
    controller.open_on_next_round()

    assert store.active_event_id() == first
    assert len(store.list_events()) == 1


def test_a_round_the_hub_cannot_fully_describe_is_never_written(wired, hub_at):
    """**The hub names a layout for only 23 of its 33 circuits.** An event
    keyed on a track with no layout files its laps under a corner model built
    for a different lap length, and nothing downstream can tell. So nothing is
    created and the round waits in the picker."""
    hub_at((("r1", SOON, INCOMPLETE),))
    controller, _, _, store = wired
    controller._on_event_saved(an_event(name="Still working on this"))
    kept = store.active_event_id()

    controller.open_on_next_round()

    assert store.active_event_id() == kept
    assert len(store.list_events()) == 1


def test_no_hub_leaves_the_app_exactly_where_it_was(wired, tmp_path,
                                                    monkeypatch):
    """The app raced for months with no hub and has to go on doing so."""
    monkeypatch.setattr(hub_read, "DEFAULT_PATH", tmp_path / "absent.db")
    controller, _, _, store = wired
    controller._on_event_saved(an_event())
    mine = store.active_event_id()

    controller.open_on_next_round()

    assert store.active_event_id() == mine
    assert len(store.list_events()) == 1


# --- the picker -------------------------------------------------------------

def _data(picker):
    return [picker.itemData(i) for i in range(picker.count())]


def test_future_rounds_are_offered_under_the_stored_events(wired, hub_at):
    hub_at((("r1", SOON, COMPLETE), ("r2", LATER, INCOMPLETE)))
    controller, event_screen, _, store = wired
    controller.open_on_next_round()
    controller.load_active_event()

    labels = [event_screen.event_picker.itemText(i)
              for i in range(event_screen.event_picker.count())]
    assert HUB_HEADING in labels
    assert NEW_EVENT in labels
    # r1 became an event, so only the later round is still an offer.
    assert "r2" in _data(event_screen.event_picker)
    assert "r1" not in _data(event_screen.event_picker)


def test_a_round_already_recorded_is_not_offered_a_second_time(wired, hub_at):
    """Listing a round both as a stored event and as an offer is how it forks
    into two events with half the laps each."""
    hub_at((("r1", SOON, COMPLETE),))
    controller, event_screen, _, store = wired
    controller.open_on_next_round()
    controller.load_active_event()

    assert "r1" not in _data(event_screen.event_picker)
    assert store.active_event_id() in _data(event_screen.event_picker)


def test_the_calendar_heading_cannot_be_selected(wired, hub_at):
    """A separator that could be chosen is a switch to nothing, and the
    picker's `itemData` is the whole vocabulary of what a selection means.

    **Asserted on the signal, not on the state behind it.** Without the guard
    the heading still emits `switched("")`, which lands in `_switch_to_round`,
    finds no such round and reloads - leaving the active event exactly where it
    was. A test watching only the active event passes either way and protects
    nothing."""
    hub_at((("r1", SOON, INCOMPLETE),))
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event())
    controller.load_active_event()

    emitted = []
    event_screen.switched.connect(emitted.append)
    picker = event_screen.event_picker
    event_screen._on_picker_activated(_data(picker).index(""))

    assert emitted == []


def test_choosing_a_complete_round_records_it_and_switches_to_it(wired,
                                                                 hub_at):
    hub_at((("r1", SOON, INCOMPLETE), ("r2", LATER, COMPLETE)))
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event(name="Something else"))
    controller.load_active_event()

    controller.switch_event("r2")

    opened = store.get_event(store.active_event_id())
    assert opened["hub_round_id"] == "r2"
    assert opened["track"] == COMPLETE


def test_choosing_an_incomplete_round_fills_the_form_and_stores_nothing(
        wired, hub_at):
    """The hub proposes and the driver disposes. The active event is cleared
    while it sits there for the same reason composing a new event clears it: a
    practice session started against an unsaved form would otherwise file its
    laps under whichever event was active before."""
    hub_at((("r1", SOON, INCOMPLETE),))
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event(name="Something else"))
    controller.load_active_event()
    before = len(store.list_events())

    controller.switch_event("r1")

    assert len(store.list_events()) == before      # nothing written
    assert store.active_event_id() is None
    # The circuit goes through; only the layout is left for him.
    assert event_screen.values()["track"] == "Nürburgring"
    assert event_screen.values()["layout"] is None
    assert event_screen.values()["hub_round_id"] == "r1"
    # And the gap is named rather than left to be discovered after saving.
    assert "pick it by hand" in event_screen.footer_note.text()


def test_a_round_that_has_left_the_calendar_says_so(wired, hub_at):
    hub_at((("r1", SOON, COMPLETE),))
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event())
    controller.load_active_event()

    controller.switch_event("gone")

    assert "no longer on the hub" in event_screen.footer_note.text()


def test_the_calendar_survives_starting_a_new_event(wired, hub_at):
    """**Four call sites used to fill this picker and three predated the
    calendar.** Whether the coming rounds were listed depended on which path
    had last refreshed the screen, and they vanished on a route as ordinary as
    clicking New event."""
    hub_at((("r1", SOON, INCOMPLETE),))
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event())
    controller.load_active_event()
    assert "r1" in _data(event_screen.event_picker)

    controller.switch_event(None)              # + New event

    assert "r1" in _data(event_screen.event_picker)


def test_a_choice_among_the_coming_rounds_survives_a_restart(wired, hub_at):
    """He asked the app to open on the next race, not to overrule him. An event
    that is itself one of the rounds still to come was picked on purpose."""
    hub_at((("r1", SOON, COMPLETE), ("r2", LATER, COMPLETE)))
    controller, _, _, store = wired
    controller.open_on_next_round()            # lands on r1, the next one
    controller.switch_event("r2")              # he deliberately moves on
    chosen = store.active_event_id()

    controller.open_on_next_round()            # "restart"

    assert store.active_event_id() == chosen


def test_the_disagreement_is_said_on_the_launch_path_not_only_on_a_switch(
        wired, hub_at):
    """**The one case the feature exists for.** Opening straight onto the round
    whose stored `mandatory_stops` disagrees with the league used to say
    nothing at all: the comparison was wired to the manual switch, and the
    launch path sets the active event and reloads without passing through it."""
    hub_at((("r1", SOON, COMPLETE),))
    controller, event_screen, _, store = wired
    # An event he already has for this round, with the league's stop count
    # wrong on it - which is the state of the real Daytona event.
    controller._on_event_saved(an_event(
        name="Round 6", track=COMPLETE, layout="Full Course",
        car_name="Lamborghini Huracan GT3", mandatory_stops=0))

    controller.open_on_next_round()
    controller.load_active_event()

    assert "mandatory stops 0 here, 1 on the hub" in event_screen.footer_note.text()


def test_an_event_left_unlinked_cannot_be_compared_against_anything(wired,
                                                                    hub_at):
    """The comparison keys on `hub_round_id`, so leaving the driver on his own
    event without linking it - which an early return once did - silently turns
    the whole report off."""
    hub_at((("r1", SOON, COMPLETE),))
    controller, _, _, store = wired
    controller._on_event_saved(an_event(
        name="Round 6", track=COMPLETE, layout="Full Course",
        car_name="Lamborghini Huracan GT3", mandatory_stops=0))
    controller.open_on_next_round()

    assert store.get_event(store.active_event_id())["hub_round_id"] == "r1"
