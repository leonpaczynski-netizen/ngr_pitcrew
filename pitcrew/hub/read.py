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
    id: str
    name: str
    status: str
    format: str | None = None
    points_scheme: tuple[int, ...] = ()
    pole_points: int = 0
    fastest_lap_points: int = 0


@dataclass(frozen=True)
class Entry:
    """One driver's registration in one series."""
    series_id: str
    driver_id: str
    driver_name: str
    car_name: str | None = None
    team: str | None = None
    status: str | None = None


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
               "fastestLapPoints FROM Series")
        if active_only:
            sql += " WHERE status = 'ACTIVE'"
        sql += " ORDER BY name"
        out = []
        for row in self._query(sql):
            out.append(Series(
                id=row["id"], name=row["name"], status=row["status"],
                format=row["format"],
                points_scheme=_as_ints(row["pointsScheme"]),
                pole_points=int(row["polePoints"] or 0),
                fastest_lap_points=int(row["fastestLapPoints"] or 0)))
        return out

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

    def results(self, series_id: str) -> list[dict]:
        """Every classified result in the league, with its penalties attached.

        One row per driver per race. `penalties` is a list of `(type, value)`
        because the hub applies them at read time and never mutates the stored
        finishing position - see `standings.effective_position`.
        """
        rows = self._query(
            """SELECT rr.id, rr.position, rr.status, rr.raceNumber,
                      rr.pole, rr.fastestLap, rr.raceClass,
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


def _as_ints(raw) -> tuple[int, ...]:
    """A Prisma JSONB integer array, however sqlite hands it over."""
    import json

    if raw is None:
        return ()
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "ignore")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return ()
    if not isinstance(raw, list):
        return ()
    out = []
    for value in raw:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            return ()
    return tuple(out)
