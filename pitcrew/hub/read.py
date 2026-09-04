"""The hub's database, opened read-only, with its age on the front.

The league hub is a Next.js app with a Prisma SQLite database beside it. Pit
Crew opens that file directly rather than keeping a copy: a copy is a thing to
forget to refresh, and a month-old duplicate answers every question with the
confidence of a current one.

### Read-only, and it is enforced rather than intended

Opened through a `file:...?mode=ro` URI, so a write raises rather than
corrupting a database another application owns. Nothing in Pit Crew has any
business changing a league result.

### Its age travels with every answer

`Hub.taken_at` is the file's own modification time - the moment of the nightly
download. Every question answered from it can say how old the answer is, which
is the difference between "P5 secures it" and "P5 secured it as of Tuesday".
A hub that has not been refreshed since before the last round is describing a
championship that has moved on, and nothing in the data itself would say so.
"""
from __future__ import annotations

import datetime
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pitcrew.diagnostics import log

_log = log(__name__)

# Where the hub lives beside this project. A sibling rather than a copy: the
# nightly download lands there and Pit Crew reads whatever is current.
DEFAULT_PATH = Path("C:/Projects/ngr_hub_project/prisma/dev.db")

# Older than this and the hub is quoted with its date attached, because a
# championship moves every round and a stale answer looks exactly like a fresh
# one.
STALE_AFTER_DAYS = 3


@dataclass(frozen=True)
class Driver:
    """One person in the league, as the hub knows them.

    `psn_name` and `driver_name` matter to Pit Crew for one reason: the
    leaderboard shows one of them, and `telemetry/roster.py` matches that
    string as a bitmap. So the hub's roster and George's are the same roster.
    """
    id: str
    driver_name: str
    psn_name: str | None = None


@dataclass(frozen=True)
class Series:
    """One league, with everything its championship actually depends on.

    **`carry_in` and `race_count` were both missing and both change results.**
    The Porsche Cup carries 17 drivers' points forward - 97 of them this
    driver's own - so without it he read as fourth on 31 points when the league
    has him leading on 128. And `raceCount` lives in the `raceConfig` JSON
    rather than in a column, so a two-race round was scoring each race at the
    full table: double the league.
    """
    id: str
    name: str
    status: str
    format: str | None = None
    points_scheme: tuple[int, ...] | None = ()
    pole_points: int = 0
    fastest_lap_points: int = 0
    class_points_scheme: tuple[int, ...] | None = ()
    class_pole_points: int = 0
    class_fl_points: int = 0
    carry_in: dict[str, int] = None
    race_count: int = 1
    # **The regulations, as the league actually publishes them.** The event row
    # is hand-typed and has been wrong about this repeatedly - `mandatory_stops
    # = 0` on a round the hub declares as a mandatory one-stop. Carried as the
    # parsed blob rather than as fields because this dataclass is the hub's
    # vocabulary, not the app's; `hub/calendar.py` owns the translation.
    lobby_settings: dict | None = None

    @property
    def multi_class(self) -> bool:
        """Whether this league is scored per class rather than outright."""
        return bool(self.format and "MULTI_CLASS" in self.format)


@dataclass(frozen=True)
class Entry:
    """One driver's registration in one series."""
    series_id: str
    driver_id: str
    driver_name: str
    car_name: str | None = None
    team: str | None = None
    status: str | None = None


@dataclass(frozen=True)
class Round:
    """One scheduled race on the league calendar.

    **`status` is not a signal.** Every one of the 57 rounds on file reads
    `SCHEDULED`, including the ones already raced, so "which round is next" is
    answered from `scheduled_at` and never from the status column. A round
    picked by status would have been round one of the season, for ever.

    `track` is the hub's own string - `"Daytona International Speedway - Road
    Course"` with an em dash. Translating it into the app's track and layout is
    `hub/calendar.py`'s job, not this module's.
    """
    id: str
    series_id: str
    series_name: str
    name: str | None
    track: str | None
    scheduled_at: datetime.datetime | None
    position: int | None = None
    # **Per-round replacement of the series defaults, and it is in use.** Four
    # rounds carry one today, including the 20 September Supercars round this
    # driver races, which overrides the series duration to 60 minutes. An
    # earlier draft of this comment said all 57 rounds override nothing; one
    # query refutes it, and the merge is load-bearing rather than speculative.
    overrides: dict | None = None


class Hub:
    """A read-only view of the league hub.

    Every method returns plain dataclasses or dicts; nothing here holds a
    cursor open. Missing is `None` and an unreadable hub is an empty answer,
    never a fabricated one - the app races perfectly well without it and did so
    for months.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self._conn: sqlite3.Connection | None = None

    # --- the connection ---------------------------------------------------

    @property
    def available(self) -> bool:
        return self.path.exists()

    @property
    def taken_at(self) -> datetime.datetime | None:
        """When this copy of the hub was written. `None` if it is not there."""
        if not self.available:
            return None
        return datetime.datetime.fromtimestamp(self.path.stat().st_mtime)

    @property
    def age_days(self) -> float | None:
        taken = self.taken_at
        if taken is None:
            return None
        return (datetime.datetime.now() - taken).total_seconds() / 86400.0

    @property
    def stale(self) -> bool:
        age = self.age_days
        return age is None or age > STALE_AFTER_DAYS

    def freshness(self) -> str:
        """One clause naming how old this answer is."""
        taken = self.taken_at
        if taken is None:
            return "the hub is not readable"
        age = self.age_days or 0.0
        if age < 1.0:
            return "hub from today"
        return f"hub from {taken:%d %b}, {age:.0f} days old"

    def _query(self, sql: str, params=()) -> list[sqlite3.Row]:
        if not self.available:
            return []
        if self._conn is None:
            try:
                self._conn = sqlite3.connect(
                    f"file:{self.path.as_posix()}?mode=ro", uri=True)
                self._conn.row_factory = sqlite3.Row
            except sqlite3.Error as exc:
                _log.warning("hub: cannot open %s: %s", self.path, exc)
                return []
        try:
            return self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            # A schema that has moved on is a real possibility - the hub is
            # another application under active development - and it must not
            # take the race down.
            _log.warning("hub: query failed (%s): %s", exc, sql.split("\n")[0])
            return []

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # --- who -------------------------------------------------------------

    def driver_by_name(self, name: str) -> Driver | None:
        """The hub driver whose displayed name matches, or `None`.

        Matched on `driverName` first and `psnName` second, because the league
        board shows the former - it is "Beeni" on screen and "Beeni-187" on
        PSN.
        """
        rows = self._query(
            "SELECT id, driverName, psnName FROM Driver "
            "WHERE driverName = ? COLLATE NOCASE "
            "   OR psnName = ? COLLATE NOCASE LIMIT 1", (name, name))
        if not rows:
            return None
        return Driver(id=rows[0]["id"], driver_name=rows[0]["driverName"],
                      psn_name=rows[0]["psnName"])

    def drivers(self) -> list[Driver]:
        return [Driver(id=r["id"], driver_name=r["driverName"],
                       psn_name=r["psnName"])
                for r in self._query(
                    "SELECT id, driverName, psnName FROM Driver "
                    "ORDER BY driverName")]

    # --- leagues ----------------------------------------------------------

    def series(self, active_only: bool = True) -> list[Series]:
        sql = ("SELECT id, name, status, format, pointsScheme, polePoints, "
               "fastestLapPoints, classPointsScheme, classPolePoints, "
               "classFlPoints, driverCarryIn, raceConfig FROM Series")
        if active_only:
            sql += " WHERE status = 'ACTIVE'"
        sql += " ORDER BY name"
        lobbies = self._lobby_settings()
        out = []
        for row in self._query(sql):
            out.append(Series(
                id=row["id"], name=row["name"], status=row["status"],
                format=row["format"],
                points_scheme=_as_ints(row["pointsScheme"]),
                pole_points=int(row["polePoints"] or 0),
                fastest_lap_points=int(row["fastestLapPoints"] or 0),
                class_points_scheme=_as_ints(row["classPointsScheme"]),
                class_pole_points=int(row["classPolePoints"] or 0),
                class_fl_points=int(row["classFlPoints"] or 0),
                carry_in=self._named_carry_in(row["driverCarryIn"]),
                race_count=_race_count(row["raceConfig"]),
                lobby_settings=lobbies.get(row["id"])))
        return out

    def _lobby_settings(self) -> dict[str, dict]:
        """Every series' published regulations, read on its own.

        **A separate query on purpose.** `_query` turns any `sqlite3.Error`
        into an empty list, deliberately, because the hub is another
        application under active development - so a column added to the shared
        `Series` SELECT means that the day the hub renames it, the standings,
        the championship line and the pit wall's roster all go silently empty
        along with the calendar. Read here, a schema change costs the feature
        that needs the column and nothing else.
        """
        try:
            return {row["id"]: _blob(row["defaultLobbySettings"])
                    for row in self._query(
                        "SELECT id, defaultLobbySettings FROM Series")}
        except Exception:                                    # noqa: BLE001
            _log.exception("hub: the lobby settings could not be read")
            return {}

    def my_series(self, driver_id: str) -> list[Series]:
        """The leagues this driver is registered in."""
        rows = self._query(
            "SELECT DISTINCT s.id FROM SeriesRegistration sr "
            "JOIN Series s ON s.id = sr.seriesId WHERE sr.driverId = ?",
            (driver_id,))
        wanted = {r["id"] for r in rows}
        return [s for s in self.series(active_only=False) if s.id in wanted]

    def entries(self, series_id: str) -> list[Entry]:
        """Everyone registered in one league, with their car and team."""
        return [Entry(series_id=series_id, driver_id=r["driverId"],
                      driver_name=r["driverName"], car_name=r["carName"],
                      team=r["team"], status=r["status"])
                for r in self._query(
                    """SELECT sr.driverId, d.driverName, sr.carName, sr.status,
                              t.name AS team
                       FROM SeriesRegistration sr
                       JOIN Driver d ON d.id = sr.driverId
                       LEFT JOIN TeamMembership tm
                              ON tm.driverId = sr.driverId
                             AND tm.seriesId = sr.seriesId
                       LEFT JOIN Team t ON t.id = tm.teamId
                       WHERE sr.seriesId = ?
                       ORDER BY d.driverName""", (series_id,))]

    def teammates(self, series_id: str, driver_id: str) -> list[str]:
        """Everyone else on this driver's team in this league.

        A list, because a team can hold more than two - the Porsche Cup entry
        has four - and "the team mate" is a question with more than one answer
        there.
        """
        return [r["driverName"] for r in self._query(
            """SELECT d.driverName
               FROM TeamMembership mine
               JOIN TeamMembership theirs
                    ON theirs.teamId = mine.teamId
                   AND theirs.seriesId = mine.seriesId
               JOIN Driver d ON d.id = theirs.driverId
               WHERE mine.driverId = ? AND mine.seriesId = ?
                 AND theirs.driverId <> mine.driverId
               ORDER BY d.driverName""", (driver_id, series_id))]

    # --- what has happened so far ----------------------------------------

    def rounds(self, series_id: str) -> list[dict]:
        return [dict(r) for r in self._query(
            "SELECT id, name, track, scheduledAt, status, position "
            "FROM Round WHERE seriesId = ? ORDER BY position, scheduledAt",
            (series_id,))]

    def upcoming_rounds(self, *, series_ids=None,
                        now: datetime.datetime | None = None,
                        include_today: bool = True) -> list[Round]:
        """The calendar from here on, soonest first.

        **Ordered and filtered by `scheduled_at`, because `status` cannot do
        it.** See `Round` - every row on file says `SCHEDULED`.

        `include_today` keeps a round scheduled earlier today in the list: the
        app is most often opened *on* race night, an hour before the lobby, and
        a calendar that drops tonight's race at one minute past its start time
        would hide the one event the driver actually wants.
        """
        now = now or datetime.datetime.now()
        floor = (now.replace(hour=0, minute=0, second=0, microsecond=0)
                 if include_today else now)
        out = []
        for row in self._query(
                "SELECT r.id, r.seriesId, r.name, r.track, r.scheduledAt, "
                "       r.position, r.lobbySettingsOverrides, "
                "       s.name AS seriesName "
                "FROM Round r JOIN Series s ON s.id = r.seriesId "
                "ORDER BY r.scheduledAt"):
            if series_ids is not None and row["seriesId"] not in series_ids:
                continue
            when = _when(row["scheduledAt"])
            # **A round with no date cannot be placed, so it is not offered.**
            # Defaulting it to now would put an undated round at the top of the
            # calendar and make it tonight's race.
            if when is None or when < floor:
                continue
            out.append(Round(
                id=row["id"], series_id=row["seriesId"],
                series_name=row["seriesName"], name=row["name"],
                track=row["track"], scheduled_at=when,
                position=row["position"],
                overrides=_blob(row["lobbySettingsOverrides"])))
        return out

    def division_layers(self, round_id: str,
                        driver_id: str | None = None) -> tuple[list, str]:
        """The division-level regulation overrides for one round, in merge order.

        **The hub lays its regulations down in four layers, not two.** The
        series publishes a default, a division may override it, the round may
        override that, and the division's own entry for the round may override
        again. Reading only the series and the round means a driver in a
        division that changes a setting is planned against a race nobody is
        running - and the Porsche Cup has exactly that shape today, with Div 2
        overriding the damage and shortcut rules.

        Returns the two division-level blobs (either may be `None`) and one
        clause saying how the division was decided, because a guess here is a
        guess about which race he is in.

        Which division is worked out in this order, and it stops at the first
        that answers:

        1. **His own sign-in for this round.** Definite.
        2. **The division he was last in for this series.** A driver is not
           usually moved between divisions mid-season, and a future round he
           has not signed into yet has no other evidence.
        3. **The only division there is.** Not an inference at all.

        None of those and it returns nothing rather than picking one: two
        divisions with different regulations is a coin toss about which race is
        being planned.
        """
        rows = self._query(
            "SELECT de.id, de.divisionId, de.lobbySettingsOverrides, "
            "       d.lobbySettingsOverrides AS divisionOverrides, "
            "       d.isDefault, d.name "
            "FROM DivisionEvent de "
            "JOIN Division d ON d.id = de.divisionId "
            "WHERE de.roundId = ?", (round_id,))
        if not rows:
            return [], "the round has no division entry"

        chosen, how = None, ""
        if driver_id:
            mine = {r["divisionEventId"] for r in self._query(
                "SELECT divisionEventId FROM EventSignIn WHERE driverId = ?",
                (driver_id,))}
            chosen = next((r for r in rows if r["id"] in mine), None)
            how = "you are signed in to it" if chosen is not None else ""
        if chosen is None and driver_id:
            seen = [r["divisionId"] for r in self._query(
                """SELECT de.divisionId FROM EventSignIn es
                   JOIN DivisionEvent de ON de.id = es.divisionEventId
                   JOIN Round r ON r.id = de.roundId
                   WHERE es.driverId = ? AND r.seriesId = (
                       SELECT seriesId FROM Round WHERE id = ?)
                   ORDER BY r.scheduledAt DESC""", (driver_id, round_id))]
            for division_id in seen:
                chosen = next((r for r in rows
                               if r["divisionId"] == division_id), None)
                if chosen is not None:
                    how = "the division you were in last round"
                    break
        if chosen is None and len(rows) == 1:
            chosen, how = rows[0], "it is the only division"
        if chosen is None:
            return [], (f"which of {len(rows)} divisions is yours is not on "
                        f"the hub - series defaults used")
        return ([_blob(chosen["divisionOverrides"]),
                 _blob(chosen["lobbySettingsOverrides"])],
                f"{chosen['name']}, {how}")

    def multi_class_car(self, series_id: str, driver_id: str,
                        round_id: str) -> tuple:
        """The car a multi-class round puts this driver in, and its class.

        **In a manufacturer series he does not register a car, he registers a
        marque.** `SeriesRegistration.carName` is NULL for every driver in the
        Enduro, which reads as "no car on the hub" and is not: the car is a
        round-by-round consequence of two other rows.

        - `MultiClassDriverRegistration` holds his `manufacturerId` - Porsche -
          and, optionally, a per-class car of his own choosing.
        - `DriverRoundClassAssignment` holds the class he is assigned **for
          this round**, and it moves: Gr.1 at Fuji, Gr.4 at Mount Panorama,
          Gr.3 at Le Mans.

        The car is then his own choice for that class if he made one, and
        otherwise his manufacturer's entry for it in `ManufacturerRoster`.
        Corroborated against the archive: Enduro Rd3 was Gr.3, the roster's
        Porsche Gr.3 is the 911 GT3 R (992) '22, and the event the driver
        recorded for that round names exactly that car.

        Returns `(car, class, why)`. `car` is `None` where any link is missing,
        and `why` says which one - a car guessed here would be a different
        category of car, not a near miss.
        """
        rows = self._query(
            "SELECT id, manufacturerId, gr1CarChoice, gr3CarChoice, "
            "       gr4CarChoice "
            "FROM MultiClassDriverRegistration "
            "WHERE seriesId = ? AND driverId = ? LIMIT 1",
            (series_id, driver_id))
        if not rows:
            return None, None, "you have no multi-class registration here"
        registration = rows[0]

        assigned = self._query(
            "SELECT assignedClass FROM DriverRoundClassAssignment "
            "WHERE mcRegistrationId = ? AND roundId = ? LIMIT 1",
            (registration["id"], round_id))
        if not assigned:
            return (None, None,
                    "the hub has not assigned you a class for this round yet")
        race_class = assigned[0]["assignedClass"]

        # "Gr.1" -> "gr1", which is how both tables spell their columns.
        key = race_class.replace(".", "").replace(" ", "").lower()
        if key not in ("gr1", "gr3", "gr4"):
            return None, race_class, f"class {race_class!r} has no car column"

        chosen = registration[f"{key}CarChoice"]
        if chosen:
            return chosen, race_class, "your own car choice for this class"

        roster = self._query(
            f"SELECT manufacturer, {key}Car AS car FROM ManufacturerRoster "
            f"WHERE id = ?", (registration["manufacturerId"],))
        if not roster or not roster[0]["car"]:
            return (None, race_class,
                    f"your manufacturer has no {race_class} car on the roster")
        return (roster[0]["car"], race_class,
                f"{roster[0]['manufacturer']}'s {race_class} car")

    def car_overrides(self, round_id: str) -> dict[str, dict]:
        """Per-car BHP and weight for one round, keyed by the hub's car name.

        This is the league's BoP for the round - 550 BHP / 1,275 kg on the
        Huracan for Daytona - and it is a round-level fact that no series
        default carries.
        """
        out: dict[str, dict] = {}
        for row in self._query(
                "SELECT carName, pp, bhp, weightKg FROM RoundCarOverride "
                "WHERE roundId = ?", (round_id,)):
            name = (row["carName"] or "").strip()
            if not name:
                continue
            out[name] = {"pp": row["pp"], "bhp": row["bhp"],
                         "weight_kg": row["weightKg"]}
        return out

    def results(self, series_id: str) -> list[dict]:
        """Every classified result in the league, with its penalties attached.

        One row per driver per race. `penalties` is a list of `(type, value)`
        because the hub applies them at read time and never mutates the stored
        finishing position - see `standings.effective_position`.
        """
        rows = self._query(
            """SELECT rr.id, rr.position, rr.status, rr.raceNumber,
                      rr.pole, rr.fastestLap, rr.raceClass,
                      rr.qualifyingPosition, rr.classQualifyingPosition,
                      d.id AS driverId, d.driverName,
                      ro.id AS roundId, ro.name AS roundName
               FROM RoundResult rr
               JOIN EventSignIn es ON es.id = rr.eventSignInId
               JOIN Driver d ON d.id = es.driverId
               JOIN DivisionEvent de ON de.id = es.divisionEventId
               JOIN Round ro ON ro.id = de.roundId
               WHERE ro.seriesId = ?
               ORDER BY ro.position, rr.raceNumber, rr.position""",
            (series_id,))
        if not rows:
            return []
        penalties: dict[str, list[tuple[str, int]]] = {}
        for row in self._query(
                "SELECT roundResultId, type, value FROM Penalty"):
            penalties.setdefault(row["roundResultId"], []).append(
                (row["type"], int(row["value"] or 0)))
        out = []
        for row in rows:
            item = dict(row)
            item["penalties"] = penalties.get(row["id"], [])
            out.append(item)
        return out

    def _named_carry_in(self, raw) -> dict[str, int]:
        """Carry-in points keyed by the driver's CURRENT name.

        **Bound entries are resolved through the `Driver` table, not read off
        the blob.** The hub matches carry-in by `driverId` first and falls back
        to the name only for unbound legacy entries, precisely so that a driver
        who has changed his displayed name keeps his points. Trusting the name
        stored in the blob would give a renamed driver two rows, each with half
        a championship, and the split is silent.
        """
        out: dict[str, int] = {}
        for driver_id, name, points in _carry_in(raw):
            if driver_id:
                rows = self._query(
                    "SELECT driverName FROM Driver WHERE id = ? LIMIT 1",
                    (driver_id,))
                if rows and rows[0]["driverName"]:
                    name = rows[0]["driverName"]
            if name:
                out[name] = out.get(name, 0) + points
        return out

    def signed_in(self, series_id: str, on_or_after=None,
                  already_run=()) -> list[str]:
        """Who has entered the next scheduled round of this league.

        **The entry list is a DECLARATION, not an observation** - a driver can
        sign in and not turn up, and four sign-ins on file are already
        NO_SHOW. It is still far better than the alternative: the only other
        source of "who is here" is the leaderboard bitmap, which needs twenty
        board frames before it will name anybody and therefore knows nobody at
        the moment the grid brief is spoken. Callers must present it as an
        entry list and never as the field.

        Reserves are included - a reserve who signed in is racing.

        **`already_run` is the only guard that works.** `Round.status` is
        `SCHEDULED` on all 57 rows in the hub, raced ones included - the column
        is never advanced - and the date test alone still matches a round that
        ran earlier the same evening. Arming after a race then narrowed the
        rival list against the field that had just finished. The caller knows
        which rounds have results; `league_for` computes exactly that set one
        line above, for `rounds_left`, and the two must agree about which round
        is next.

        Ordered by `position` first, like `rounds()`, so two rounds sharing a
        date - the Enduro ran twice on 25 July - are taken in the league's own
        order rather than an arbitrary one.
        """
        when = on_or_after or datetime.datetime.now()
        done = set(already_run or ())
        rounds = self._query(
            "SELECT id, scheduledAt FROM Round WHERE seriesId = ? "
            "AND scheduledAt IS NOT NULL AND status != 'COMPLETED' "
            "ORDER BY position ASC, scheduledAt ASC", (series_id,))
        for row in rounds:
            if row["id"] in done:
                continue
            try:
                due = datetime.datetime.fromisoformat(
                    str(row["scheduledAt"]).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if due.tzinfo is not None:
                due = due.astimezone().replace(tzinfo=None)
            if due.date() < when.date():
                continue
            names = self._query(
                "SELECT d.driverName FROM EventSignIn es "
                "JOIN DivisionEvent de ON de.id = es.divisionEventId "
                "JOIN Driver d ON d.id = es.driverId "
                "WHERE de.roundId = ? AND es.status = 'CONFIRMED'",
                (row["id"],))
            if names:
                return [str(r["driverName"]) for r in names
                        if r["driverName"]]
        return []

    def hidden_drivers(self) -> set[str]:
        """Normalised names of drivers the league hides from its standings.

        **A banned driver is not a title rival and never will be again.** The
        hub filters every league-facing standings surface through
        `getHiddenDrivers()`; Pit Crew did not, so a banned driver sat in the
        table shifting every position below him by one and appeared in the
        spoken "watch" list - telling the driver to defend a championship
        against somebody who cannot score, which is the exact cost the rival
        filter exists to avoid.

        Mirrors `ban.ts`: emails compared trimmed and lower-cased, and the
        owner is never hidden whatever the ban list says.
        """
        rows = self._query(
            "SELECT d.driverName FROM Driver d "
            "JOIN User u ON u.id = d.userId "
            "WHERE u.isOwner IS NOT 1 AND u.email IS NOT NULL "
            "  AND lower(trim(u.email)) IN "
            "      (SELECT lower(trim(email)) FROM BannedEmail)")
        return {str(r["driverName"]).strip().lower() for r in rows
                if r["driverName"]}

    def precomputed_points(self, series_id: str) -> dict[str, int]:
        """The hub's own persisted points per result id, where it has them.

        `sumBreakdown` in `points.ts` adds all FOUR components - the overall
        finish score and the three class ones - and the file says every
        aggregation surface should prefer that total verbatim rather than
        re-deriving it. Present only for MULTI_CLASS_MANUFACTURER results.

        A row missing any component is skipped rather than part-summed:
        CLAUDE.md rule 3, since a partial total is indistinguishable from a
        low one.
        """
        parts = ("overallFinishPoints", "classFinishPoints",
                 "classPolePoints", "classFlPoints")
        out: dict[str, int] = {}
        for row in self.class_breakdowns(series_id).values():
            if any(row.get(name) is None for name in parts):
                continue
            try:
                out[row["roundResultId"]] = sum(int(row[n]) for n in parts)
            except (TypeError, ValueError):
                continue
        return out

    def class_breakdowns(self, series_id: str) -> dict:
        """The hub's own pre-computed breakdown rows for a multi-class round.

        Keyed by result id. `precomputed_points` is what callers want.
        """
        return {r["roundResultId"]: dict(r) for r in self._query(
            """SELECT b.* FROM MultiClassResultBreakdown b
               JOIN RoundResult rr ON rr.id = b.roundResultId
               JOIN EventSignIn es ON es.id = rr.eventSignInId
               JOIN DivisionEvent de ON de.id = es.divisionEventId
               JOIN Round ro ON ro.id = de.roundId
               WHERE ro.seriesId = ?""", (series_id,))}

    def round_run_since(self, series_id: str, when) -> bool:
        """Whether a round has been run since `when`.

        **The staleness test that matters.** A flat day count calls a two-day
        old copy current; if a round ran last night it is describing a
        championship that has already moved, and nothing in the data says so.
        """
        if when is None:
            return True
        return any(_after(row["scheduledAt"], when) for row in self._query(
            "SELECT scheduledAt FROM Round WHERE seriesId = ? "
            "AND scheduledAt IS NOT NULL", (series_id,)))


def _after(raw, when) -> bool:
    """Whether a stored timestamp falls between `when` and now.

    **Both sides on the local clock.** `scheduledAt` is stored UTC and
    `taken_at` is a file mtime read as naive LOCAL time; comparing them raw
    put a 9.5 h skew between the two - wider than the gap between a round
    finishing and the nightly copy landing, which is the entire window this
    exists to detect. The league's rounds are stored at 10:30 UTC, 20:30
    local, squarely inside it.
    """
    try:
        ran = datetime.datetime.fromisoformat(
            str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if ran.tzinfo is not None:
        ran = ran.astimezone().replace(tzinfo=None)
    return when < ran < datetime.datetime.now()


def _blob(raw) -> dict | None:
    """A JSON column as a dict, or `None` where it is not one.

    **`None` and not `{}`.** Most rounds store the literal string `"null"` in
    `lobbySettingsOverrides`; an empty dict would read as "this round overrides
    nothing", which is the same answer in effect but not the same claim, and
    the merge distinguishes them.
    """
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _when(raw) -> datetime.datetime | None:
    """A hub timestamp as a naive local-ish datetime, or `None`.

    **Converted to local time, not stripped of its offset.** `_after` above
    already learned this the hard way - its docstring records a 9.5 h skew on
    these exact rows, because the league stores its rounds at 10:30 UTC and
    races them at 20:30 local. Dropping the offset here rather than converting
    it put every calendar row ten hours early: survivable while that stays on
    the same date, and wrong by a whole day for any round after about 22:00
    local, which then also vanishes from the calendar on the morning of its
    own race.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime.datetime):
        return (raw.astimezone().replace(tzinfo=None)
                if raw.tzinfo is not None else raw)
    try:
        parsed = datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.replace(tzinfo=None)


def _as_ints(raw) -> tuple[int, ...] | None:
    """A Prisma JSONB integer array, or `None` if it could not be read.

    **`None` and `()` are different answers and must not collapse.** An empty
    array means "this league uses the default table"; a blob that would not
    parse means "I do not know what this league uses", and returning `()` for
    both made an unreadable 44-point-a-win scheme silently score 22.
    CLAUDE.md rule 3.
    """
    import json

    if raw is None:
        return ()
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "ignore")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(raw, list):
        return None
    out = []
    for value in raw:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            return None
    return tuple(out)


def _carry_in(raw) -> list[tuple[str | None, str, int]]:
    """Points carried into a league, as (driver id, name, points).

    The Porsche Cup carries seventeen drivers forward and this driver's own
    entry is 97 points - most of his total. Reading the table without it put
    him fourth on 31 where the league has him leading on 128.

    The id is kept because the hub matches on it first; `Hub._named_carry_in`
    resolves it to the driver's current name.
    """
    import json

    if raw is None:
        return []
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "ignore")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, list):
        return []
    out: list[tuple[str | None, str, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("driverName")
        try:
            points = int(item.get("points") or 0)
        except (TypeError, ValueError):
            continue
        if name:
            out.append((item.get("driverId") or None, str(name), points))
    return out


def _race_count(raw) -> int:
    """Races per round, from the `raceConfig` JSON rather than a column.

    Defaults to one. A two-race round divides the finishing scheme, and
    scoring each race at the full table doubles the league.
    """
    import json

    if raw is None:
        return 1
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "ignore")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return 1
    if not isinstance(raw, dict):
        return 1
    try:
        return max(1, int(raw.get("raceCount") or 1))
    except (TypeError, ValueError):
        return 1
