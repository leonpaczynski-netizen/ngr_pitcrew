"""Reading the league hub's nightly copy.

Everything here was untested when a review found four defects in it, three of
which changed what the driver was told. The pattern that hid them: the link and
standings tests stub the hub out, so the layer that actually talks to SQLite -
which round is next, whose points carry in, who is banned - was exercised by
nothing at all.

A real SQLite file, because the defects were in the SQL and in the shape of the
data, and a fake would have reproduced neither.
"""
from __future__ import annotations

import datetime
import sqlite3

import pytest

from pitcrew.hub.read import Hub, _after, _carry_in


SCHEMA = """
CREATE TABLE Series (id TEXT PRIMARY KEY, name TEXT, status TEXT, format TEXT,
    pointsScheme TEXT, polePoints INT, fastestLapPoints INT,
    classPointsScheme TEXT, classPolePoints INT, classFlPoints INT,
    driverCarryIn TEXT, raceConfig TEXT);
CREATE TABLE Driver (id TEXT PRIMARY KEY, userId TEXT, driverName TEXT,
    psnName TEXT);
CREATE TABLE User (id TEXT PRIMARY KEY, email TEXT, isOwner INT);
CREATE TABLE BannedEmail (id TEXT PRIMARY KEY, email TEXT);
CREATE TABLE Round (id TEXT PRIMARY KEY, seriesId TEXT, name TEXT,
    scheduledAt TEXT, status TEXT, position INT);
CREATE TABLE DivisionEvent (id TEXT PRIMARY KEY, roundId TEXT);
CREATE TABLE EventSignIn (id TEXT PRIMARY KEY, divisionEventId TEXT,
    driverId TEXT, status TEXT);
"""


def a_hub(tmp_path, *, rounds=(), signins=(), banned=(), carry_in=None):
    """A hub file with just enough in it to answer one question."""
    path = tmp_path / "dev.db"
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO Series (id, name, status, driverCarryIn) "
               "VALUES ('s1', 'A League', 'ACTIVE', ?)", (carry_in,))
    for who, email, owner in (("Beeni", "b@x.com", 0), ("Rocky", "r@x.com", 0),
                              ("Boss", "boss@x.com", 1),
                              ("Pooy01", "p@x.com", 0)):
        db.execute("INSERT INTO User VALUES (?, ?, ?)", (who, email, owner))
        db.execute("INSERT INTO Driver VALUES (?, ?, ?, ?)",
                   (who, who, who, f"{who}-187"))
    for email in banned:
        db.execute("INSERT INTO BannedEmail VALUES (?, ?)", (email, email))
    for rid, when, position in rounds:
        db.execute("INSERT INTO Round VALUES (?, 's1', ?, ?, 'SCHEDULED', ?)",
                   (rid, rid, when, position))
        db.execute("INSERT INTO DivisionEvent VALUES (?, ?)",
                   (f"de-{rid}", rid))
    for n, (rid, who, status) in enumerate(signins):
        db.execute("INSERT INTO EventSignIn VALUES (?, ?, ?, ?)",
                   (f"si{n}", f"de-{rid}", who, status))
    db.commit()
    db.close()
    return Hub(path)


# --- which round is next ----------------------------------------------------

ROUNDS = (("r1", "2026-08-31T10:30:00.000+00:00", 1),
          ("r2", "2026-09-07T10:30:00.000+00:00", 2))
SIGNINS = (("r1", "Beeni", "CONFIRMED"), ("r1", "Rocky", "CONFIRMED"),
           ("r1", "Pooy01", "NO_SHOW"),
           ("r2", "Beeni", "CONFIRMED"))


def test_a_round_that_ran_earlier_today_is_not_the_next_round(tmp_path):
    """**`Round.status` never advances** - every one of the 57 rows in the real
    hub says SCHEDULED, raced ones included - so the date test alone still
    matched a round that had already run. Arming again on a race evening then
    narrowed the rival list against the field that had just finished.
    """
    hub = a_hub(tmp_path, rounds=ROUNDS, signins=SIGNINS)
    evening = datetime.datetime(2026, 8, 31, 22, 0)
    assert sorted(hub.signed_in("s1", on_or_after=evening)) == \
        ["Beeni", "Rocky"]                       # the race just run
    assert hub.signed_in("s1", on_or_after=evening, already_run={"r1"}) == \
        ["Beeni"]                                # the one still to come


def test_two_rounds_on_one_day_are_taken_in_the_leagues_own_order(tmp_path):
    """The Enduro ran twice on 25 July. Ordered by date alone the two are
    indistinguishable; `position` is what the league itself uses."""
    # The league's order and the clock's order deliberately DISAGREE: round
    # one is the later race of the day. Ordered by `scheduledAt` this returns
    # Rocky, so the test discriminates rather than merely passing.
    same_day = (("round-one", "2026-09-07T11:00:00.000+00:00", 1),
                ("round-two", "2026-09-07T06:00:00.000+00:00", 2))
    hub = a_hub(tmp_path, rounds=same_day,
                signins=(("round-one", "Beeni", "CONFIRMED"),
                         ("round-two", "Rocky", "CONFIRMED")))
    assert hub.signed_in("s1", on_or_after=datetime.datetime(2026, 9, 1)) \
        == ["Beeni"]


def test_only_confirmed_entries_count(tmp_path):
    """A no-show is not on the grid. On a FUTURE round nobody is marked yet,
    so this filter does nothing there and the list stays a declaration - which
    is what the caller is told to present it as."""
    hub = a_hub(tmp_path, rounds=ROUNDS, signins=SIGNINS)
    assert "Pooy01" not in hub.signed_in(
        "s1", on_or_after=datetime.datetime(2026, 8, 31, 22, 0))


def test_a_league_with_no_signed_in_round_says_so_rather_than_guessing(
        tmp_path):
    hub = a_hub(tmp_path, rounds=ROUNDS)
    assert hub.signed_in("s1") == []


# --- who is hidden ----------------------------------------------------------

def test_a_banned_driver_is_hidden_and_the_owner_never_is(tmp_path):
    """`ban.ts` compares emails trimmed and lower-cased and skips the owner
    whatever the ban list says - locking the league owner out of his own
    standings is the one failure this must not have."""
    hub = a_hub(tmp_path, banned=("  P@X.COM  ", "boss@x.com"))
    assert hub.hidden_drivers() == {"pooy01"}


def test_no_ban_list_hides_nobody(tmp_path):
    assert a_hub(tmp_path).hidden_drivers() == set()


# --- points carried in ------------------------------------------------------

def test_carry_in_keeps_the_driver_id_so_a_rename_cannot_split_him(tmp_path):
    """The hub matches carry-in by id FIRST, precisely so a driver who has
    changed his displayed name keeps his points. Trusting the name written on
    the blob would give him two rows with half a championship each."""
    blob = ('[{"driverId": "Beeni", "driverName": "OldName", "points": 97},'
            ' {"driverName": "Rocky", "points": 88}]')
    hub = a_hub(tmp_path, carry_in=blob)
    series = hub.series()[0]
    assert series.carry_in == {"Beeni": 97, "Rocky": 88}


def test_a_carry_in_blob_that_will_not_parse_is_empty_rather_than_wrong():
    assert _carry_in("not json at all") == []
    assert _carry_in(None) == []
    assert _carry_in('{"not": "a list"}') == []


def test_an_entry_without_a_name_is_dropped_and_the_rest_survive():
    assert _carry_in('[{"points": 5}, {"driverName": "Rocky", "points": 88}]') \
        == [(None, "Rocky", 88)]


# --- the clock --------------------------------------------------------------

def test_a_stored_utc_timestamp_is_compared_on_the_local_clock():
    """`taken_at` is a file mtime read as naive LOCAL time and `scheduledAt` is
    stored UTC. Compared raw they were 9.5 h apart on this machine - wider than
    the gap between a round finishing and the nightly copy landing, which is
    the entire window the staleness check exists to detect.
    """
    stored = "2026-08-31T10:30:00.000+00:00"
    local = datetime.datetime.fromisoformat(stored).astimezone()
    just_before = local.replace(tzinfo=None) - datetime.timedelta(minutes=5)
    just_after = local.replace(tzinfo=None) + datetime.timedelta(minutes=5)
    assert _after(stored, just_before)
    assert not _after(stored, just_after)


def test_an_unreadable_timestamp_is_not_a_round_having_run():
    assert not _after("whenever", datetime.datetime(2026, 1, 1))
    assert not _after(None, datetime.datetime(2026, 1, 1))


# --- the file itself --------------------------------------------------------

def test_a_hub_that_is_not_there_answers_everything_emptily(tmp_path):
    """The app raced for months with no hub and must go on doing so."""
    hub = Hub(tmp_path / "nothing.db")
    assert not hub.available
    assert hub.series() == [] and hub.hidden_drivers() == set()
    assert hub.signed_in("s1") == []
