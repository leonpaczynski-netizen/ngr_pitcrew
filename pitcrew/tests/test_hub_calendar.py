"""The league calendar, and the translation between two vocabularies.

The hub says `RACING_SOFT`, `GRID_FALSE_START` and
`"Daytona International Speedway - Road Course"`; the event row says `RS`,
`"Grid - no track limit"`, and a track and a layout in two columns. Everything
here is about that seam, because a mistranslation in it is silent: a compound
the strategy engine cannot plan on, or a mandatory stop read as none.
"""
from __future__ import annotations

import datetime
import json
import sqlite3

from pitcrew.hub.calendar import (
    Proposal,
    _merge,
    next_round,
    regulations,
    resolve_track,
    upcoming,
)
from pitcrew.hub.read import Hub

SCHEMA = """
CREATE TABLE Series (id TEXT PRIMARY KEY, name TEXT, status TEXT, format TEXT,
    pointsScheme TEXT, polePoints INT, fastestLapPoints INT,
    classPointsScheme TEXT, classPolePoints INT, classFlPoints INT,
    driverCarryIn TEXT, raceConfig TEXT, defaultLobbySettings TEXT);
CREATE TABLE Driver (id TEXT PRIMARY KEY, userId TEXT, driverName TEXT,
    psnName TEXT);
CREATE TABLE Round (id TEXT PRIMARY KEY, seriesId TEXT, name TEXT,
    scheduledAt TEXT, status TEXT, position INT, track TEXT,
    lobbySettingsOverrides TEXT);
CREATE TABLE RoundCarOverride (id TEXT PRIMARY KEY, roundId TEXT,
    carName TEXT, pp INT, bhp INT, weightKg INT);
CREATE TABLE SeriesRegistration (id TEXT PRIMARY KEY, seriesId TEXT,
    driverId TEXT, carName TEXT, status TEXT);
CREATE TABLE TeamMembership (id TEXT PRIMARY KEY, teamId TEXT, seriesId TEXT,
    driverId TEXT);
CREATE TABLE Team (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE Division (id TEXT PRIMARY KEY, seriesId TEXT, name TEXT,
    isDefault INT, lobbySettingsOverrides TEXT, position INT);
CREATE TABLE DivisionEvent (id TEXT PRIMARY KEY, roundId TEXT,
    divisionId TEXT, lobbySettingsOverrides TEXT);
CREATE TABLE EventSignIn (id TEXT PRIMARY KEY, divisionEventId TEXT,
    driverId TEXT, status TEXT);
CREATE TABLE MultiClassDriverRegistration (id TEXT PRIMARY KEY,
    seriesRegistrationId TEXT, seriesId TEXT, driverId TEXT,
    manufacturerId TEXT, mcRegStatus TEXT, gr1CarChoice TEXT,
    gr3CarChoice TEXT, gr4CarChoice TEXT);
CREATE TABLE DriverRoundClassAssignment (id TEXT PRIMARY KEY,
    mcRegistrationId TEXT, roundId TEXT, assignedClass TEXT);
CREATE TABLE ManufacturerRoster (id TEXT PRIMARY KEY, seriesId TEXT,
    manufacturer TEXT, gr1Car TEXT, gr3Car TEXT, gr4Car TEXT,
    isAvailable INT);
"""

# A circuit the app knows at a layout it does not - the hub's Nurburgring
# "Endurance II" has no entry in `catalogs`. This is what genuinely
# unresolvable looks like now that a bare circuit name means its base layout.
PART_KNOWN = "N\u00fcrburgring \u2014 Endurance II"

GR3 = {
    "raceFormat": {"raceType": "LAPS", "lapCount": 20},
    "timeWeather": {"weatherMode": "RANDOM", "timeOfDay": "AFTERNOON",
                    "variableTimeSpeedRate": 2},
    "tyresFuel": {"tyreWearEnabled": True, "tyreWearMultiplier": 2,
                  "fuelEnabled": True, "fuelMultiplier": 3, "refuelRate": 1},
    "carRegulations": {
        "allowedTyreCompounds": ["RACING_SOFT", "RACING_MEDIUM",
                                 "RACING_HARD"],
        # Two leagues on the real hub carry one of these, and it is the field
        # the form cannot edit - so it is in the fixture to keep the carried
        # path honest rather than for decoration.
        "requiredTyreCompound": ["RACING_SOFT", "RACING_MEDIUM"]},
    "gridStart": {"startType": "STANDING", "mandatoryPitStops": True,
                  "minPitStopCount": 1},
    "drivingAssists": {"absLimit": "NO_LIMIT",
                       "countersteeringAssistLimit": "PROHIBITED"},
}

EM_DASH = "—"


def a_manufacturer_hub(tmp_path, *, rounds=(), assignments=(), choice=None,
                       roster=("Porsche 963 '24", "Porsche 911 GT3 R (992) '22",
                               "Porsche Cayman GT4 Clubsport '16")):
    """A multi-class series where the driver registers a marque, not a car.

    This is the Enduro's shape: `SeriesRegistration.carName` is NULL for every
    driver in it, and the car is a consequence of the manufacturer he
    registered and the class he is assigned for the round.
    """
    # **Registered, with a NULL car.** That is the real shape: every driver in
    # the Enduro has a `SeriesRegistration` row and none of them names a car.
    # Skipping the row entirely would have made him unregistered, which is a
    # different thing and takes a different branch.
    hub = a_hub(tmp_path, rounds=rounds, reg_car=None,
                series_format="MULTI_CLASS_MANUFACTURER")
    db = sqlite3.connect(hub.path)
    db.execute("INSERT INTO ManufacturerRoster VALUES "
               "('m1', 's1', 'Porsche', ?, ?, ?, 1)", roster)
    db.execute("INSERT INTO MultiClassDriverRegistration VALUES "
               "('mc1', NULL, 's1', 'd1', 'm1', 'CONFIRMED', ?, ?, ?)",
               (choice or None, None, None))
    for n, (round_id, race_class) in enumerate(assignments):
        db.execute("INSERT INTO DriverRoundClassAssignment VALUES "
                   "(?, 'mc1', ?, ?)", (f"a{n}", round_id, race_class))
    db.commit()
    db.close()
    return hub


_MARQUE = object()          # "registered, but the hub names no car"


def a_hub(tmp_path, *, rounds=(), lobby=GR3, registered=True, cars=(),
          series_format=None, reg_car=_MARQUE):
    path = tmp_path / "dev.db"
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    for series in ("s1", "s2"):
        db.execute(
            "INSERT INTO Series (id, name, status, format, "
            "defaultLobbySettings) VALUES (?, ?, 'ACTIVE', ?, ?)",
            (series, f"League {series}", series_format,
             json.dumps(lobby) if lobby else None))
    db.execute("INSERT INTO Driver VALUES ('d1', 'u1', 'Beeni', 'Beeni-187')")
    if registered:
        db.execute("INSERT INTO SeriesRegistration "
                   "VALUES ('sr1', 's1', 'd1', ?, 'CONFIRMED')",
                   ("Lamborghini Huracan GT3" if reg_car is _MARQUE
                    else reg_car,))
    for rid, series, when, track in rounds:
        db.execute("INSERT INTO Round VALUES "
                   "(?, ?, ?, ?, 'SCHEDULED', 1, ?, 'null')",
                   (rid, series, rid, when, track))
    for n, (rid, car, bhp, kg) in enumerate(cars):
        db.execute("INSERT INTO RoundCarOverride VALUES (?, ?, ?, NULL, ?, ?)",
                   (f"co{n}", rid, car, bhp, kg))
    db.commit()
    db.close()
    return Hub(path)


NOW = datetime.datetime(2026, 9, 5, 9, 0)
# Relative to the day the test runs. The sibling constants in
# `test_hub_events` were fixed dates, went past, and took eleven tests red on
# a day nobody touched them.
def _round_at(days: int) -> str:
    when = (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=days)).replace(
        hour=10, minute=30, second=0, microsecond=0)
    return when.strftime("%Y-%m-%dT%H:%M:%S.000+00:00")


SOON = _round_at(7)
LATER = _round_at(14)
PAST = "2026-08-31T10:30:00.000+00:00"


# --- the track string -------------------------------------------------------

def test_the_hubs_em_dash_still_finds_the_apps_en_dash_layout():
    """**Two catalogues that chose different dashes.** The hub writes its
    layouts after an em dash and `catalogs.LAYOUT_SEPARATOR` is an en dash, so
    a split on the app's separator matched nothing and every multi-layout
    circuit on the calendar - 17 of 33 - lost its layout."""
    match = resolve_track(
        f"Daytona International Speedway {EM_DASH} Road Course")
    assert (match.track, match.layout) == (
        "Daytona International Speedway", "Road Course")
    assert match.complete


def test_a_circuit_whose_own_name_holds_a_hyphen_is_not_split_on_it():
    """`Sardegna - Road Track` is one circuit in the catalogue, hyphen and all.
    Normalising separators before testing the whole string as a track turned it
    into a track called `Sardegna` that does not exist."""
    assert resolve_track("Sardegna - Road Track").track == "Sardegna - Road Track"


def test_a_bare_circuit_name_is_the_base_layout_and_not_a_missing_one():
    """**The hub's format is documented, and a string with no separator parses
    as the `Default` variant** - `gt7-tracks.ts` says so, and calls the format
    stable enough that changing it would be a data migration.

    Read as "the hub declined to name a layout", it made 10 of the 33 circuits
    on the calendar unresolvable when every one had been stated."""
    assert resolve_track(
        "Michelin Raceway Road Atlanta").layout == "Full Course"
    assert resolve_track(
        "Fuji International Speedway").layout == "Full Course"
    assert resolve_track("Autodromo Nazionale Monza").layout == "Full Course"
    # Spa's base layout is the Full Course, not the 24h.
    assert resolve_track(
        "Circuit de Spa-Francorchamps").layout == "Full Course"


def test_the_base_layout_is_taken_positionally_and_not_by_its_name():
    """Both catalogues list layouts in the game's own order, which is what
    lets `Default` resolve at all. It is `Full Course` almost everywhere and
    `Layout A` at Sardegna - Road Track, so matching on the words would have
    left that circuit with no base layout."""
    assert resolve_track("Sardegna - Road Track").layout == "Layout A"
    assert resolve_track(
        "Sardegna - Road Track \u2014 Reverse").layout == "Layout A (Reverse)"
    assert resolve_track(
        "Sardegna - Road Track \u2014 Layout B Reverse"
    ).layout == "Layout B (Reverse)"


def test_the_two_catalogues_punctuate_a_reversed_layout_differently():
    """The hub writes `"<layout> Reverse"`; the app writes
    `"<layout> (Reverse)"`. The same fact, spelled two ways."""
    assert resolve_track(
        "Deep Forest Raceway \u2014 Reverse").layout == "Full Course (Reverse)"
    assert resolve_track(
        "Autodrome Lago Maggiore \u2014 Centre Reverse"
    ).layout == "Centre (Reverse)"


def test_an_unmatched_circuit_keeps_no_half_answer():
    match = resolve_track("Nowhere Special")
    assert (match.track, match.layout) == (None, None)
    assert match.why


def test_an_unmatched_layout_still_yields_its_circuit():
    """Half an answer the driver completes beats none: he is the one looking at
    the lobby, and the circuit was never in doubt.

    `Endurance II` is a real hub layout with no entry in the app's catalogue,
    so this is the shape a genuine mismatch takes rather than an invented one."""
    match = resolve_track(PART_KNOWN)
    assert match.track == "N\u00fcrburgring"
    assert match.layout is None
    assert not match.complete


# --- the regulations --------------------------------------------------------

def test_a_mandatory_stop_is_one_stop_and_not_none():
    """**The defect this whole feature exists to remove.** The stored Daytona
    event says `mandatory_stops = 0` on a round the league publishes as a
    mandatory one-stop, and that figure is an input to the strategy engine."""
    assert regulations(GR3)["mandatory_stops"] == 1


def test_no_mandatory_stop_is_a_real_zero_and_silence_is_absence():
    """`False` means the league has said "none required"; a blob that does not
    mention stops has said nothing. The strategy engine must tell them apart -
    one means no stop is ever forced, the other means nobody knows."""
    assert regulations(
        {"gridStart": {"mandatoryPitStops": False}})["mandatory_stops"] == 0
    assert "mandatory_stops" not in regulations({"gridStart": {}})


def test_a_missing_stop_count_still_means_at_least_one_stop():
    """Reading the absent count as zero is exactly how a mandatory one-stop
    round came to be recorded as needing no stops."""
    assert regulations(
        {"gridStart": {"mandatoryPitStops": True}})["mandatory_stops"] == 1


def test_the_refuel_rate_is_litres_per_second_and_says_where_it_came_from():
    """**Two different quantities that both live under `tyresFuel`.**
    `refuelRate` is litres per second and `fuelMultiplier` is a rate
    multiplier; the app has a column for each. The hub's `1` for this league is
    corroborated by the app's own Daytona measurement of 1.003 L/s.

    The source matters as much as the number: `refuel_rate_lps` is NOT NULL
    with a default of 2.5, so without a provenance beside it a league figure
    and the schema's placeholder are the same number to every reader. `hub` is
    neither `measured` - nobody measured it - nor `declared`, which would claim
    the driver typed it."""
    regs = regulations(GR3)
    assert regs["refuel_rate_lps"] == 1.0
    assert regs["refuel_rate_source"] == "hub"
    assert regs["fuel_mult"] == "3x"          # the multiplier, separately


def test_no_refuel_rate_is_carried_into_a_league_that_has_fuel_off():
    """A league that has switched fuel off has no refuelling to have a rate
    for, and a rate carried into such an event prices a stop that cannot
    happen."""
    regs = regulations({"tyresFuel": {"fuelEnabled": False, "refuelRate": 3}})
    assert "refuel_rate_lps" not in regs
    assert "refuel_rate_source" not in regs


def test_only_a_prohibition_says_what_the_driver_is_running():
    """`NO_LIMIT` says the league permits ABS. It does not say what he runs,
    and the column is what he runs."""
    regs = regulations(GR3)
    assert "abs_setting" not in regs          # absLimit is NO_LIMIT
    assert regs["countersteer"] == 0          # and this one is PROHIBITED

    off = regulations({"drivingAssists": {
        "absLimit": "PROHIBITED", "tractionControlLimit": "PROHIBITED"}})
    assert off["abs_setting"] == "Off"
    assert off["tcs"] == 0


def test_wear_switched_off_is_not_the_same_answer_as_wear_unmentioned():
    assert regulations(
        {"tyresFuel": {"tyreWearEnabled": False}})["tyre_wear_mult"] == "Off"
    assert "tyre_wear_mult" not in regulations({"tyresFuel": {}})
    assert regulations(GR3)["tyre_wear_mult"] == "2x"


def test_compounds_arrive_as_the_codes_the_strategy_engine_keys_on():
    assert regulations(GR3)["available_compounds"] == ["RS", "RM", "RH"]


def test_an_unmappable_compound_is_dropped_rather_than_passed_through():
    """A `RACING_SOFT` reaching the strategy engine unmapped is not a compound
    it can plan a stint on."""
    assert regulations({"carRegulations": {
        "allowedTyreCompounds": ["RACING_SOFT", "MOON_TYRE"]},
    })["available_compounds"] == ["RS"]


def test_a_timed_race_puts_its_minutes_where_the_app_reads_them():
    """`race_minutes` is never written - `race/coordinator.py` says so - and
    the controller reads the one figure against `race_type`."""
    regs = regulations({"raceFormat": {"raceType": "TIMED",
                                       "durationMinutes": 50}})
    assert (regs["race_type"], regs["race_laps"]) == ("time", 50)


def test_a_round_override_replaces_one_field_and_keeps_its_neighbours():
    """The blob is two levels deep, so a shallow update would let a round that
    overrides one tyre field discard every other field in that section."""
    merged = _merge(GR3, {"tyresFuel": {"fuelMultiplier": 5}})
    assert merged["tyresFuel"]["fuelMultiplier"] == 5
    assert merged["tyresFuel"]["tyreWearMultiplier"] == 2
    assert regulations(merged)["fuel_mult"] == "5x"


# --- the calendar -----------------------------------------------------------

def test_the_calendar_is_narrowed_to_the_leagues_he_is_entered_in(tmp_path):
    hub = a_hub(tmp_path, rounds=(("r1", "s1", SOON, "Suzuka Circuit"),
                                  ("r2", "s2", SOON, "Suzuka Circuit")))
    assert [p.round_id for p in upcoming(hub, me="Beeni", now=NOW)] == ["r1"]
    hub.close()


def test_without_a_name_every_active_league_is_offered_and_it_says_so(tmp_path):
    """A calendar showing four leagues he can pick from is a smaller failure
    than an empty screen, and the reason it shows four is fixable."""
    hub = a_hub(tmp_path, rounds=(("r1", "s1", SOON, "Suzuka Circuit"),
                                  ("r2", "s2", SOON, "Suzuka Circuit")))
    everything = upcoming(hub, me=None, now=NOW)
    assert {p.round_id for p in everything} == {"r1", "r2"}
    assert any("no hub driver name is set" in u
               for u in everything[0].unknowns)
    hub.close()


def test_a_round_already_raced_is_not_on_the_calendar(tmp_path):
    hub = a_hub(tmp_path, rounds=(("old", "s1", PAST, "Suzuka Circuit"),
                                  ("new", "s1", SOON, "Suzuka Circuit")))
    assert [p.round_id for p in upcoming(hub, me="Beeni", now=NOW)] == ["new"]
    hub.close()


def test_the_next_round_is_the_soonest_and_nothing_cleverer(tmp_path):
    """Ranking by how much the app knows would open on a well-documented round
    three weeks out while tonight's race sat further down the list."""
    hub = a_hub(tmp_path, rounds=(
        ("later", "s1", LATER,
         f"Daytona International Speedway {EM_DASH} Road Course"),
        ("soon", "s1", SOON, PART_KNOWN)))
    nxt = next_round(upcoming(hub, me="Beeni", now=NOW))
    assert nxt.round_id == "soon"
    assert not nxt.known           # and it is still the next one
    hub.close()


def test_a_round_already_recorded_carries_its_event_id(tmp_path):
    """So that selecting tonight's race twice loads the event the second time
    instead of forking the round into two."""
    hub = a_hub(tmp_path, rounds=(("r1", "s1", SOON, "Suzuka Circuit"),))
    got = upcoming(hub, me="Beeni", now=NOW,
                   stored_events=[{"id": 7, "hub_round_id": "r1"}])
    assert got[0].event_id == 7
    hub.close()


def test_the_rounds_own_bop_reaches_the_proposal(tmp_path):
    """550 BHP / 1,275 kg on the Huracan for Daytona is a round-level fact that
    no series default carries."""
    hub = a_hub(tmp_path, rounds=(("r1", "s1", SOON, "Suzuka Circuit"),),
                cars=(("r1", "Lamborghini Huracan GT3", 550, 1275),))
    got = upcoming(hub, me="Beeni", now=NOW)[0]
    assert (got.bhp, got.weight_kg) == (550, 1275)
    assert got.car_name == "Lamborghini Huracan GT3"
    hub.close()


def test_no_hub_file_is_an_empty_calendar_and_never_a_raise(tmp_path):
    """The app raced for months with no hub and has to go on doing so."""
    assert upcoming(Hub(tmp_path / "absent.db"), me="Beeni", now=NOW) == []


def test_the_event_row_carries_the_round_id_even_when_incomplete():
    """`hub_round_id` is what makes the round findable again after the driver
    renames the event, so it is written whatever else is missing."""
    fields = Proposal(
        round_id="r9", series_id="s1", series_name="A League",
        round_name="Rd6", scheduled_at=None,
        track="Fuji International Speedway", layout=None).event_fields()
    assert fields["hub_round_id"] == "r9"
    assert fields["name"] == "A League Rd6"
    assert fields["series"] == "A League"
    assert "layout" not in fields          # absent, never an empty string


# --- events from before the calendar existed --------------------------------

def _stored(**overrides):
    event = {"id": 10, "hub_round_id": None,
             "track": "Michelin Raceway Road Atlanta", "layout": "Full Course",
             "car_name": "Lamborghini Huracan GT3"}
    event.update(overrides)
    return event


def test_the_event_he_already_has_here_is_adopted_and_not_duplicated(tmp_path):
    """**Every event on file predates the calendar and carries no round id.**
    Without a match on circuit and car, each one is offered as a round with no
    event and created a second time the moment it is picked - leaving the
    practice laps on one copy and the race on the other."""
    hub = a_hub(tmp_path, rounds=(
        ("r1", "s1", SOON, "Michelin Raceway Road Atlanta"),))
    got = upcoming(hub, me="Beeni", now=NOW, stored_events=[_stored()])[0]
    assert got.event_id == 10
    assert got.adopted
    hub.close()


def test_two_candidates_are_a_coin_toss_and_adopt_nothing(tmp_path):
    """The bar `league_for` sets for matching a league by its car, for the same
    reason: a round bound to the wrong event puts this week's laps into last
    month's aggregate where nothing can separate them again."""
    hub = a_hub(tmp_path, rounds=(
        ("r1", "s1", SOON, "Michelin Raceway Road Atlanta"),))
    got = upcoming(hub, me="Beeni", now=NOW,
                   stored_events=[_stored(), _stored(id=11)])[0]
    assert got.event_id is None
    assert not got.adopted
    hub.close()


def test_a_different_car_at_the_same_circuit_is_a_different_event(tmp_path):
    hub = a_hub(tmp_path, rounds=(
        ("r1", "s1", SOON, "Michelin Raceway Road Atlanta"),))
    got = upcoming(hub, me="Beeni", now=NOW, stored_events=[
        _stored(car_name="Ford Shelby GT350R '16")])[0]
    assert got.event_id is None
    hub.close()


def test_an_unresolved_layout_adopts_nothing(tmp_path):
    """Without a layout the pair does not identify a circuit, and Spa's Full
    Course and its 24h Layout are different tracks with different lap lengths
    and different corner models."""
    hub = a_hub(tmp_path, rounds=(("r1", "s1", SOON, PART_KNOWN),))
    got = upcoming(hub, me="Beeni", now=NOW, stored_events=[
        _stored(track="N\u00fcrburgring", layout=None)])[0]
    assert got.event_id is None
    hub.close()


def test_one_event_cannot_answer_for_two_rounds(tmp_path):
    """The earlier round takes it, which is the right way round - it is the one
    whose laps already exist."""
    hub = a_hub(tmp_path, rounds=(
        ("early", "s1", SOON, "Michelin Raceway Road Atlanta"),
        ("late", "s1", LATER, "Michelin Raceway Road Atlanta")))
    got = upcoming(hub, me="Beeni", now=NOW, stored_events=[_stored()])
    assert [p.event_id for p in got] == [10, None]


def test_an_event_already_linked_is_matched_by_its_id_not_by_its_circuit(
        tmp_path):
    """The id is exact and survives a rename, a track correction, or a change
    of car. The circuit match is the fallback for events that predate it."""
    hub = a_hub(tmp_path, rounds=(
        ("r1", "s1", SOON, "Michelin Raceway Road Atlanta"),))
    got = upcoming(hub, me="Beeni", now=NOW, stored_events=[
        _stored(id=42, hub_round_id="r1", track="Renamed", layout="Other")])[0]
    assert got.event_id == 42
    assert not got.adopted        # nothing to write back
    hub.close()


def test_a_round_with_no_name_is_named_from_its_place_in_the_season():
    """The name has to be derived and stable. Falling back to the date would
    move the event's name when a round is rescheduled, and every session
    recorded under it would stop matching."""
    unnamed = Proposal(
        round_id="r9", series_id="s1", series_name="A League",
        round_name=None, scheduled_at=None, track="X", layout="Y", position=6)
    assert unnamed.name == "A League Rd6"
    assert Proposal(
        round_id="r9", series_id="s1", series_name="A League",
        round_name=None, scheduled_at=None, track="X",
        layout="Y").name == "A League"


# --- the four layers the hub lays its regulations down in --------------------

def test_the_regulations_are_merged_in_the_hubs_own_order():
    """**Series, then division, then round, then that division's own entry for
    the round.** Reading only the first and third means a driver in a division
    that changes a setting is planned against a race nobody is running."""
    merged = _merge(
        {"tyresFuel": {"tyreWearMultiplier": 2, "fuelMultiplier": 3,
                       "tyreWearEnabled": True, "fuelEnabled": True}},
        {"tyresFuel": {"tyreWearMultiplier": 4}},      # the division
        {"tyresFuel": {"fuelMultiplier": 5}},          # the round
        {"tyresFuel": {"tyreWearMultiplier": 6}})      # the division's entry
    regs = regulations(merged)
    assert regs["tyre_wear_mult"] == "6x"   # last layer wins
    assert regs["fuel_mult"] == "5x"        # and the round's survives it


def test_a_later_layer_replaces_one_field_without_clearing_its_neighbours():
    merged = _merge({"tyresFuel": {"tyreWearMultiplier": 2, "fuelEnabled": True,
                                   "tyreWearEnabled": True,
                                   "fuelMultiplier": 3}},
                    None, {"tyresFuel": {"fuelMultiplier": 5}}, None)
    assert merged["tyresFuel"]["tyreWearMultiplier"] == 2


def test_a_mandated_drivetrain_is_a_reading_and_an_unrestricted_one_is_not():
    """GT7 broadcasts no drivetrain channel, so the column is declared or it is
    unknown. Where the league restricts entries to one layout every car in the
    race is that layout - a reading. No restriction says nothing at all about
    what he drives, and a guess there would silence `wheelspin`'s disclosure
    that it is watching all four wheels."""
    assert regulations({"carRegulations": {"drivetrainLimit": "MR"}
                        })["drivetrain"] == "MR"
    assert "drivetrain" not in regulations({"carRegulations": {}})
    assert "drivetrain" not in regulations(
        {"carRegulations": {"drivetrainLimit": "ANYTHING"}})


# --- a manufacturer series names a marque, not a car ------------------------

def test_the_car_comes_from_the_marque_and_the_class_he_is_assigned(tmp_path):
    """**`SeriesRegistration.carName` is NULL for every driver in the Enduro**,
    which reads as "no car on the hub" and is not. He registers Porsche; the
    class he is assigned for the round decides which Porsche.

    Corroborated against the archive: Enduro Rd3 was Gr.3, the roster's Porsche
    Gr.3 is the 911 GT3 R (992) '22, and the event recorded for that round
    names exactly that car."""
    hub = a_manufacturer_hub(
        tmp_path,
        rounds=(("r1", "s1", SOON, "Suzuka Circuit"),),
        assignments=(("r1", "Gr.1"),))
    got = upcoming(hub, me="Beeni", now=NOW)[0]
    assert got.car_name == "Porsche 963 '24"
    assert got.race_class == "Gr.1"
    hub.close()


def test_the_class_moves_between_rounds_and_the_car_moves_with_it(tmp_path):
    """Which class he races when is part of the strategy, so the car is a
    per-round fact and cannot be cached against the series."""
    hub = a_manufacturer_hub(
        tmp_path,
        rounds=(("r1", "s1", SOON, "Suzuka Circuit"),
                ("r2", "s1", LATER, "Mount Panorama Circuit")),
        assignments=(("r1", "Gr.1"), ("r2", "Gr.4")))
    got = upcoming(hub, me="Beeni", now=NOW)
    assert [p.car_name for p in got] == [
        "Porsche 963 '24", "Porsche Cayman GT4 Clubsport '16"]
    assert [p.race_class for p in got] == ["Gr.1", "Gr.4"]
    hub.close()


def test_his_own_car_choice_beats_the_manufacturers_roster(tmp_path):
    """`gr1CarChoice` is unused across all ten registrations today, but it is
    the schema's way of letting a driver name his own car for a class - so it
    is read first rather than assumed absent."""
    hub = a_manufacturer_hub(
        tmp_path,
        rounds=(("r1", "s1", SOON, "Suzuka Circuit"),),
        assignments=(("r1", "Gr.1"),), choice="Porsche 919 Hybrid '16")
    assert upcoming(hub, me="Beeni",
                    now=NOW)[0].car_name == "Porsche 919 Hybrid '16"
    hub.close()


def test_a_round_with_no_class_assigned_yet_has_no_car_and_says_which_link(
        tmp_path):
    """A car guessed here would be a different *category* of car, not a near
    miss - a Gr.1 prototype where a Gr.4 hatch belongs."""
    hub = a_manufacturer_hub(
        tmp_path, rounds=(("r1", "s1", SOON, "Suzuka Circuit"),),
        assignments=())
    got = upcoming(hub, me="Beeni", now=NOW)[0]
    assert got.car_name is None
    assert not got.known
    assert any("not assigned you a class" in u for u in got.unknowns)
    hub.close()


def test_a_class_whose_car_the_roster_does_not_carry_is_refused(tmp_path):
    hub = a_manufacturer_hub(
        tmp_path, rounds=(("r1", "s1", SOON, "Suzuka Circuit"),),
        assignments=(("r1", "Gr.3"),), roster=("Porsche 963 '24", None, None))
    got = upcoming(hub, me="Beeni", now=NOW)[0]
    assert got.car_name is None
    assert any("no Gr.3 car on the roster" in u for u in got.unknowns)
    hub.close()


def test_the_car_regulations_reach_the_event_row():
    """Porsche Cup: 509 BHP / 1,243 kg. Absent stays absent, never zero."""
    from pitcrew.hub.calendar import regulations

    out = regulations({"carRegulations": {"powerLimitBhp": 509,
                                          "weightLimitKg": "1243",
                                          "drivetrainLimit": "MR"}})
    assert out["power_limit_bhp"] == 509.0
    assert out["weight_limit_kg"] == 1243.0
    assert "power_limit_bhp" not in regulations({"carRegulations": {}})
    assert "weight_limit_kg" not in regulations({"carRegulations": {
        "weightLimitKg": None}})


def test_bop_and_open_tuning_reach_the_event_row(tmp_path):
    """Plan row 2.7: the Enduro runs BoP (`bopEnabled: true`), which locks the
    gearbox and the power adjustments, and `initial` had to ask because the
    app had no field. Only a real boolean is written; silence stays NULL."""
    from pitcrew.hub.calendar import regulations
    from pitcrew.store.db import Store

    enduro = regulations({"carRegulations": {"bopEnabled": True,
                                             "tuningAllowed": True}})
    assert (enduro["bop_enabled"], enduro["tuning_allowed"]) == (1, 1)
    closed = regulations({"carRegulations": {"bopEnabled": False,
                                             "tuningAllowed": False}})
    assert (closed["bop_enabled"], closed["tuning_allowed"]) == (0, 0)
    assert "bop_enabled" not in regulations({"carRegulations": {}})
    assert "bop_enabled" not in regulations({"carRegulations": {
        "bopEnabled": "true"}}), "a word is not the hub saying yes"

    store = Store(tmp_path / "bop.db")
    try:
        event_id = store.create_event(name="Fuji Enduro", track="Fuji",
                                      **enduro)
        row = store.get_event(event_id)
        assert (row["bop_enabled"], row["tuning_allowed"]) == (1, 1)
        other = store.create_event(name="GR3", track="Fuji")
        assert store.get_event(other)["bop_enabled"] is None
    finally:
        store.close()
