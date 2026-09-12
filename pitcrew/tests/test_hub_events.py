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


def test_bop_survives_the_calendar_pick_of_an_incomplete_round(
        wired, tmp_path, monkeypatch):
    """The critic on row 2.7, BLOCKER (its repro, kept). Every Enduro round
    arrives incomplete - no legal compounds on the hub - so it goes pick ->
    fill the compounds -> Save, and that save dropped BoP: the Fuji event
    would have said "ask him" after the hub had said yes."""
    enduro = {**GR3, "carRegulations": {"bopEnabled": True,
                                        "tuningAllowed": True,
                                        "powerLimitBhp": 509,
                                        "weightLimitKg": 1243}}
    enduro["gridStart"] = {"startType": "ROLLING", "mandatoryPitStops": False}
    path = tmp_path / "league.db"
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO Series (id, name, status, defaultLobbySettings) "
               "VALUES ('s1','NGR GR3','ACTIVE',?)", (json.dumps(enduro),))
    db.execute("INSERT INTO Driver VALUES ('d1','u1','Beeni','Beeni-187')")
    db.execute("INSERT INTO SeriesRegistration VALUES "
               "('sr1','s1','d1','Lamborghini Huracan GT3','OK')")
    db.execute("INSERT INTO Round VALUES ('r1','s1','r1',?,'SCHEDULED',1,"
               "'Fuji International Speedway','null')", (SOON,))
    db.commit()
    db.close()
    monkeypatch.setattr(hub_read, "DEFAULT_PATH", path)
    controller, event_screen, _, store = wired

    controller.switch_event("r1")
    assert store.active_event_id() is None, "an incomplete round waits for him"
    # **The save path alone** (pass 2, minor 1): with the round still on the
    # hub, the load after the save filled the values back in and the test
    # passed without the save fix. The hub stops listing it before Save.
    monkeypatch.setattr(controller, "hub_proposals", lambda: [])
    controller._on_event_saved({**an_event(), **event_screen.values(),
                                "available_compounds": ["RH", "RM", "RS"]})
    saved = store.get_event(store.active_event_id())
    assert (saved["bop_enabled"], saved["tuning_allowed"]) == (1, 1)
    assert saved["power_limit_bhp"] == 509.0
    assert saved["weight_limit_kg"] == 1243.0


# A second circuit, for the tests that need two rounds at once.
ELSEWHERE = "Circuit de Spa-Francorchamps"


def _hub_stating(tmp_path, monkeypatch, rounds, *, name="regs", **regs):
    """A hub whose series states BoP and the limits.

    `hub_at` builds the plain GR3 series, which states none of the four
    hub-only columns - and those columns are what these tests are about.
    """
    blob = {**GR3, "carRegulations": {**GR3.get("carRegulations", {}), **regs}}
    path = tmp_path / f"{name}.db"
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO Series (id, name, status, defaultLobbySettings) "
               "VALUES ('s1', 'NGR GR3', 'ACTIVE', ?)", (json.dumps(blob),))
    db.execute("INSERT INTO Driver VALUES ('d1', 'u1', 'Beeni', 'Beeni-187')")
    db.execute("INSERT INTO SeriesRegistration VALUES "
               "('sr1', 's1', 'd1', 'Lamborghini Huracan GT3', 'OK')")
    for rid, track in rounds:
        db.execute("INSERT INTO Round VALUES "
                   "(?, 's1', ?, ?, 'SCHEDULED', 1, ?, 'null')",
                   (rid, rid, SOON, track))
    db.commit()
    db.close()
    monkeypatch.setattr(hub_read, "DEFAULT_PATH", path)
    return path


def _mine(controller, store, name, track):
    """An event of his own at that circuit, in the car he is registered in -
    which is what makes the calendar infer the link."""
    controller._on_event_saved(an_event(
        name=name, track=track, layout="Full Course",
        car_name="Lamborghini Huracan GT3"))
    return store.active_event_id()


def _link_all(controller):
    """The launch path's inference, without the launch."""
    for proposal in controller.hub_proposals():
        if proposal.event_id is not None:
            controller._link_round(proposal)


def test_a_switch_says_the_hub_news_instead_of_overwriting_it(
        wired, tmp_path, monkeypatch):
    """**The critic on row 2.7, pass 5, MAJOR** (its repro, kept).

    `switch_event` rebuilt the footer out of its own regulation comparison and
    wrote it over the one `load_active_event` had just composed. The
    comparison survived that, because the switch did it again; everything else
    did not - above all "From the hub: BoP is now on for this round", which is
    the whole of row 2.7's news, appears on no other screen, and cannot be
    said a second time: the round has been spent and the stored value now
    agrees with the hub. On the ordinary route between two events he was told
    nothing, while the sheet quietly changed underneath him.
    """
    _hub_stating(tmp_path, monkeypatch, (("r1", COMPLETE), ("r2", ELSEWHERE)),
                 bopEnabled=True, powerLimitBhp=509)
    controller, event_screen, _, store = wired
    mine = _mine(controller, store, "Mine A", COMPLETE)
    _mine(controller, store, "Mine B", ELSEWHERE)
    _link_all(controller)

    controller.switch_event(mine)

    footer = event_screen.footer_note.text()
    assert "Working on Mine A" in footer            # the switch's own line
    assert "From the hub:" in footer                # and the load's, kept
    assert "linked to" in footer
    assert "BoP is now on for this round" in footer
    assert store.get_event(mine)["bop_enabled"] == 1


def test_a_round_whose_write_failed_is_still_known_to_be_inferred(
        wired, tmp_path, monkeypatch):
    """**Pass 5, minor 2.** The round was spent above the write it justifies,
    so an `update_event` that raised left the row unwritten, the footer silent
    and the link unsayable ever after - the one thing that knew the match was
    inferred having already been thrown away."""
    _hub_stating(tmp_path, monkeypatch, (("r1", COMPLETE),),
                 bopEnabled=True, powerLimitBhp=509)
    controller, event_screen, _, store = wired
    mine = _mine(controller, store, "Mine A", COMPLETE)
    _link_all(controller)

    def boom(*args, **kwargs):
        raise RuntimeError("the database went away")

    # Restored by hand, not with `monkeypatch.undo()`: that would put the
    # hub's path back as well, and the second half of this test needs the hub.
    wrote = store.update_event
    store.update_event = boom
    try:
        controller.load_active_event()
    finally:
        store.update_event = wrote

    assert "r1" in controller._adopted_rounds, "spent on a write that failed"
    assert store.get_event(mine)["bop_enabled"] is None

    controller.load_active_event()

    footer = event_screen.footer_note.text()
    assert "linked to" in footer and "BoP is now on" in footer
    assert store.get_event(mine)["bop_enabled"] == 1
    assert "r1" not in controller._adopted_rounds, "and spent once it lands"


def test_an_event_that_already_agrees_is_told_it_was_linked_and_spends_it(
        wired, tmp_path, monkeypatch):
    """**Pass 5, minor 3.** The link was said only alongside a fill, and the
    round was spent only alongside one - so an event whose stored values
    already matched the hub was never told it had been matched at all, and
    kept the round remembered indefinitely. The next genuine change, whole
    loads later, was then announced as a fresh link: "linked to NGR GR3 Rd 6
    by circuit and car; BoP is now off", crediting a match that had nothing to
    do with it. The link is news on its own."""
    _hub_stating(tmp_path, monkeypatch, (("r1", COMPLETE),), name="on",
                 bopEnabled=True, powerLimitBhp=509)
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event(
        name="Mine A", track=COMPLETE, layout="Full Course",
        car_name="Lamborghini Huracan GT3",
        bop_enabled=1, power_limit_bhp=509.0))
    _link_all(controller)

    controller.load_active_event()                  # nothing to fill

    assert "linked to" in event_screen.footer_note.text()
    assert "r1" not in controller._adopted_rounds

    # The league turns BoP off. That is a change, and only a change.
    # Nothing to invalidate: `hub_proposals` re-reads the file every call, on
    # purpose - a cache there would be state outliving a session.
    _hub_stating(tmp_path, monkeypatch, (("r1", COMPLETE),), name="off",
                 bopEnabled=False, powerLimitBhp=509)
    controller.load_active_event()

    footer = event_screen.footer_note.text()
    assert "BoP is now off for this round" in footer
    assert "linked to" not in footer, "a change is not a fresh match"


def test_spending_one_inferred_round_does_not_spend_the_other(
        wired, tmp_path, monkeypatch):
    """**Pass 5, minor 4** - the discard was pinned by nothing, and three
    mutants lived: never spending, spending every remembered round, and
    dropping the discard while keeping the notes. Each round is spent by its
    own event's load, and by no other."""
    _hub_stating(tmp_path, monkeypatch, (("r1", COMPLETE), ("r2", ELSEWHERE)),
                 bopEnabled=True, powerLimitBhp=509)
    controller, event_screen, _, store = wired
    first = _mine(controller, store, "Mine A", COMPLETE)
    second = _mine(controller, store, "Mine B", ELSEWHERE)
    _link_all(controller)
    assert controller._adopted_rounds == {"r1", "r2"}

    controller.switch_event(first)

    assert controller._adopted_rounds == {"r2"}, "one load, one round spent"
    assert "linked to" in event_screen.footer_note.text()

    controller.switch_event(second)

    assert controller._adopted_rounds == set()
    assert "linked to" in event_screen.footer_note.text()

    controller.switch_event(first)

    assert "linked to" not in event_screen.footer_note.text(), "said once"


def _notes(event_screen):
    """What the controller asks the footer to say, and how.

    The warning is written straight through `set_ink` and cannot be read back
    off the widget, so the flag is pinned where it is decided.
    """
    said = []
    wrote = event_screen.note

    def spy(text, *, warn=False):
        said.append((text, warn))
        wrote(text, warn=warn)

    event_screen.note = spy
    return said


def test_the_hub_news_does_not_leak_onto_the_next_event(
        wired, tmp_path, monkeypatch):
    """**The critic on row 2.7, pass 6, minor 1.** `_calendar_news` is
    assigned unconditionally, `([], False)` included, and that assignment is
    the whole of what stops one event's news being prefixed to the next
    event's footer. Moving it inside `if said:` passes every other test - and
    it is CLAUDE.md rule 11 exactly: state that outlives what it describes,
    read as if it belonged to this event."""
    _hub_stating(tmp_path, monkeypatch, (("r1", COMPLETE),),
                 bopEnabled=True, powerLimitBhp=509)
    controller, event_screen, _, store = wired
    mine = _mine(controller, store, "Mine A", COMPLETE)
    controller._on_event_saved(an_event(name="Hand typed B"))
    hand = store.active_event_id()
    _link_all(controller)
    controller.switch_event(mine)
    assert "BoP is now on" in event_screen.footer_note.text()

    controller.switch_event(hand)

    footer = event_screen.footer_note.text()
    assert "Working on Hand typed B" in footer
    assert "BoP is now" not in footer, "the last event's news, on this one"
    assert "linked to" not in footer


def test_the_hub_news_reaches_the_switch_footer_as_a_warning(
        wired, tmp_path, monkeypatch):
    """**Pass 6, minor 2.** A BoP change arriving on the switch path styled
    as an ordinary note is the news the driver scrolls past."""
    _hub_stating(tmp_path, monkeypatch, (("r1", COMPLETE),),
                 bopEnabled=True, powerLimitBhp=509)
    controller, event_screen, _, store = wired
    mine = _mine(controller, store, "Mine A", COMPLETE)
    _link_all(controller)
    said = _notes(event_screen)

    controller.switch_event(mine)

    # **Selected by what it says, not by being last** (pass 6 review): a note
    # appended after this one would make `said[-1]` follow it silently
    # instead of failing.
    text, warn = next(note for note in said if "Working on" in note[0])
    assert "BoP is now on" in text and warn, (text, warn)


def test_the_adopted_link_footer_keeps_its_warning(
        wired, tmp_path, monkeypatch):
    """**Pass 6, minor 3** - and the mistake my own first attempt made. The
    adopted branch appends to the switch's footer; appending without carrying
    `warn` demotes a warning to a note, which is the same loss of the news in
    a quieter form."""
    _hub_stating(tmp_path, monkeypatch, (("r1", COMPLETE),),
                 bopEnabled=True, powerLimitBhp=509)
    controller, event_screen, _, store = wired
    _mine(controller, store, "Mine A", COMPLETE)
    said = _notes(event_screen)

    controller.switch_event("r1")            # the calendar's own route in

    text, warn = next(note for note in said if "not a second copy" in note[0])
    assert "BoP is now on" in text, "the news the append was writing over"
    assert warn, "a warning, appended to, is still a warning"


def test_a_round_stating_none_of_the_four_still_spends_its_link(
        wired, hub_at):
    """**Pass 6, minor 4.** The states-none early return discards too, and
    nothing asserted it - so pass 5's staleness could come back for exactly
    the rounds the plain league series produces, which is most of them."""
    hub_at((("r1", SOON, COMPLETE),))         # GR3 states none of the four
    controller, event_screen, _, store = wired
    _mine(controller, store, "Mine A", COMPLETE)
    _link_all(controller)
    assert controller._adopted_rounds == {"r1"}

    controller.load_active_event()

    assert controller._adopted_rounds == set()


def test_the_footer_paints_a_warning_as_a_warning(qt_app):
    """**The other side of the seam** (the pass-6 review's own limit).

    Every test above pins what the controller ASKS the footer for, which is
    where all three defects of this class happened. None of them would notice
    a widget that stopped honouring `warn` - the critic proved it with a
    mutant inking `CHALK` unconditionally, which survived the lot. So the
    rendering is pinned too, the way `test_banner.py` pins its side.
    """
    from pitcrew.ui import theme

    screen = EventScreen()
    screen.note("Working on Mine A. No practice laps recorded yet.")
    assert theme.WARNING not in screen.footer_note.styleSheet()

    screen.note("From the hub: BoP is now on for this round.", warn=True)
    assert theme.WARNING in screen.footer_note.styleSheet()


def _bop_hub(tmp_path, monkeypatch, *, bop=True, tuning=True, power=None,
             weight=None, name="bop-league.db"):
    """A one-round hub with these car regulations."""
    cars = {**GR3.get("carRegulations", {}), "bopEnabled": bop,
            "tuningAllowed": tuning}
    if power is not None:
        cars["powerLimitBhp"] = power
    if weight is not None:
        cars["weightLimitKg"] = weight
    blob = {**GR3, "carRegulations": cars}
    path = tmp_path / name
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO Series (id, name, status, defaultLobbySettings) "
               "VALUES ('s1','NGR GR3','ACTIVE',?)", (json.dumps(blob),))
    db.execute("INSERT INTO Driver VALUES ('d1','u1','Beeni','Beeni-187')")
    db.execute("INSERT INTO SeriesRegistration VALUES "
               "('sr1','s1','d1','Lamborghini Huracan GT3','OK')")
    db.execute("INSERT INTO Round VALUES ('r1','s1','r1',?,'SCHEDULED',1,?,"
               "'null')", (SOON, COMPLETE))
    db.commit()
    db.close()
    monkeypatch.setattr(hub_read, "DEFAULT_PATH", path)


def test_a_linked_event_follows_the_hub_and_says_what_changed(
        wired, tmp_path, monkeypatch):
    """The critic on row 2.7: M1, nothing wrote the hub's BoP onto a stored
    event; pass 2's BLOCKER, the first word the hub said was then kept for
    good as if it were his - BoP turned on after he saved and Ludo was still
    handed "off", and a new power limit went unsaid. No screen writes these
    columns, so the hub's current word wins and a change is said."""
    _bop_hub(tmp_path, monkeypatch, bop=False, power=509, weight=1243)
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event(
        name="Round 6", track=COMPLETE, layout="Full Course",
        car_name="Lamborghini Huracan GT3", hub_round_id="r1"))
    event_id = store.active_event_id()
    got = store.get_event(event_id)
    assert (got["bop_enabled"], got["power_limit_bhp"],
            got["weight_limit_kg"]) == (0, 509.0, 1243.0)

    # The league turns BoP on and moves both limits.
    _bop_hub(tmp_path, monkeypatch, bop=True, tuning=False, power=520,
             weight=1250, name="bop-league-2.db")
    controller.load_active_event()
    got = store.get_event(event_id)
    assert (got["bop_enabled"], got["tuning_allowed"], got["power_limit_bhp"],
            got["weight_limit_kg"]) == (1, 0, 520.0, 1250.0)
    said = event_screen.footer_note.text()
    for words in ("BoP is now on", "tuning is now closed",
                  "power limit now 520 BHP (was 509)",
                  "weight limit now 1250 kg (was 1243)"):
        assert words in said, (words, said)
    # Never the raw form ("BoP 0 here, 1 on the hub", pass 2 minor 2); the
    # boxed fields keep their own comparison, which does read "here/on the hub".
    assert "BoP 0" not in said and "BoP 1" not in said
    assert "open tuning" not in said
    # The form loaded after the hub's word, so a Save carries it, not the
    # stale copy (the pass-2 ordering).
    assert event_screen.values()["bop_enabled"] == 1
    assert event_screen.values()["power_limit_bhp"] == 520.0


def test_an_inferred_link_says_the_regulations_it_brings(
        wired, tmp_path, monkeypatch):
    """The critic on row 2.7, pass 4 (MAJOR): a link matched by circuit and
    car writes the round's BoP onto HIS event, and said nothing - a first
    fill is deliberately not news. The `adopted` flag could not carry that,
    because the link is written before the load that applies them."""
    _bop_hub(tmp_path, monkeypatch, bop=True, power=509)
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event(
        name="Round 6", track=COMPLETE, layout="Full Course",
        car_name="Lamborghini Huracan GT3"))          # no hub_round_id
    event_id = store.active_event_id()
    assert store.get_event(event_id)["bop_enabled"] is None

    controller.open_on_next_round()
    controller.load_active_event()

    got = store.get_event(event_id)
    assert (got["hub_round_id"], got["bop_enabled"]) == ("r1", 1)
    said = event_screen.footer_note.text()
    assert "linked to" in said and "by circuit and car" in said
    assert "BoP is now on for this round" in said
    assert "power limit now 509 BHP, not stated before" in said
    # Spent once: the next load is not news again.
    controller.load_active_event()
    assert "linked to" not in event_screen.footer_note.text()


def test_a_first_fill_on_a_link_he_made_is_not_news(wired, tmp_path,
                                                    monkeypatch):
    """The other side of it: where the round id is his, the hub filling a
    column he was never asked about changes no instruction."""
    _bop_hub(tmp_path, monkeypatch, bop=True)
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event(
        name="Round 6", track=COMPLETE, layout="Full Course",
        car_name="Lamborghini Huracan GT3", hub_round_id="r1"))
    assert store.get_event(store.active_event_id())["bop_enabled"] == 1
    assert "From the hub" not in event_screen.footer_note.text()


def test_a_round_that_states_no_regulations_writes_nothing(
        wired, tmp_path, monkeypatch):
    """Silence is not a change (pass 3). The comparison still runs."""
    path = tmp_path / "bare-league.db"
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO Series (id, name, status, defaultLobbySettings) "
               "VALUES ('s1','NGR GR3','ACTIVE',?)",
               (json.dumps({**GR3, "carRegulations": {}}),))
    db.execute("INSERT INTO Driver VALUES ('d1','u1','Beeni','Beeni-187')")
    db.execute("INSERT INTO SeriesRegistration VALUES "
               "('sr1','s1','d1','Lamborghini Huracan GT3','OK')")
    db.execute("INSERT INTO Round VALUES ('r1','s1','r1',?,'SCHEDULED',1,?,"
               "'null')", (SOON, COMPLETE))
    db.commit()
    db.close()
    monkeypatch.setattr(hub_read, "DEFAULT_PATH", path)
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event(
        name="Round 6", track=COMPLETE, layout="Full Course",
        car_name="Lamborghini Huracan GT3", hub_round_id="r1",
        mandatory_stops=0))
    got = store.get_event(store.active_event_id())
    assert (got["bop_enabled"], got["power_limit_bhp"]) == (None, None)
    # ...and the boxed fields are still compared.
    assert "mandatory stops" in event_screen.footer_note.text()


def test_a_write_that_fails_says_nothing_it_did_not_do(wired, tmp_path,
                                                       monkeypatch):
    """Pass 3, minor 2: the notes are worded BEFORE the write, so a failure
    there must leave the row, the form and what he is told in step."""
    _bop_hub(tmp_path, monkeypatch, bop=False, power=509)
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event(
        name="Round 6", track=COMPLETE, layout="Full Course",
        car_name="Lamborghini Huracan GT3", hub_round_id="r1"))
    event_id = store.active_event_id()
    _bop_hub(tmp_path, monkeypatch, bop=True, power=520,
             name="bare-league-2.db")

    def refuse(*args, **kwargs):
        raise sqlite3.OperationalError("no")

    monkeypatch.setattr(store, "update_event", refuse)
    controller.load_active_event()
    monkeypatch.undo()
    got = store.get_event(event_id)
    assert (got["bop_enabled"], got["power_limit_bhp"]) == (0, 509.0)
    assert "BoP is now on" not in event_screen.footer_note.text()


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
