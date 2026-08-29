"""SQLite store for Pit Crew.

One small class with explicit methods, in contrast to the 11,000-line god-class
it replaces.  If a method here starts needing a paragraph of explanation it
probably belongs in the layer above.

Concurrency: sqlite is opened with `check_same_thread=False` because laps are
written from the telemetry thread while the UI reads on the Qt thread, and
every write goes through `_write()` which holds a lock for the transaction.
"""
from __future__ import annotations

import datetime
import json
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from pitcrew.diagnostics import log
from pitcrew.paths import DATA_DIR
from pitcrew.store.schema import ADDED_COLUMNS, DDL, MIGRATIONS, SCHEMA_VERSION

DEFAULT_DB_PATH = DATA_DIR / "pitcrew.db"

# **Where a tyre-wear reading came from.** Both are the same instrument - the
# in-game gauge - and neither is derived, so neither is second-class evidence.
# They are kept apart because they have different shapes: the driver's is a
# glance at a moving car that lands once or twice a stint, the video's is
# quantised to the gauge's 30 pixels and lands as often as the capture is
# sampled. A model that could not tell them apart could not explain why one
# stint carries eighty readings and another carries one.
#
# Null in the column means `driver`: nothing else could have written a reading
# before the column existed.
WEAR_DRIVER = "driver"
WEAR_HUD_VIDEO = "hud-video"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# The two event constants the driver types, and the column that says whether he
# did.  Both value columns are NOT NULL with an app default, so `None` from the
# form cannot be stored as itself; it is recorded as an absent provenance and
# the value column keeps whatever it held.  Nothing may read the number as his
# without checking the source first.
_DECLARED_CONSTANTS = {
    "refuel_rate_lps": "refuel_rate_source",
    "pit_loss_secs": "pit_loss_source",
}


# **Which sessions a race plan may be costed on**, in one place because it is
# one policy and it is easy to state twice and differently.
#
# **A contradiction disqualifies a session. An absence does not.** That is the
# whole rule, and the two halves are different kinds of fact:
#
# * `car-mismatch` - the wire named a car, and it was not this event's car.
#   That is positive evidence that these laps were turned by something else,
#   and it is why the gate exists at all: session 11 streamed `GR3` on a road-
#   car event and its lap 4 burn of 7.563377380371094 L became
#   `assumptions.fuelPerLapL = 7.563` in the approved plan.
# * `car-unknown` - the wire named a car nothing on file claims, so the session
#   is linked to a quarantined `cars` row. Also a contradiction of a sort: the
#   event declares a canonical car and this is provably not it.
# * `no-reading` - the wire named nothing. GT7 was not streaming, or the packet
#   landed before the car loaded, which is also why those runs read a 0 L tank.
#   **This is the absence of evidence, not evidence of absence.** The event
#   already declares its car; an unlabelled session under it is not a session
#   contradicting it. Excluding on a field that never populated is precisely
#   the failure CLAUDE.md rule 3 names - treating missing as a value - and it
#   was measured to make the answer worse, not safer: event 2's burn reads
#   7.638 L with these sessions held out and 7.178 with them in, while the race
#   itself burned 6.57-7.00. Discarding a valid Shelby run because a packet
#   field was empty is a real loss for no gain.
#
# None of the three is a deletion in any case. Every lap reads back through
# `list_laps` and `list_event_laps` and the export still describes them; what
# an excluded session does not do is cost a stop.
EVIDENCE_IDENTITY_SQL = (
    "COALESCE(sessions.identity_status, 'ok') "
    "NOT IN ('car-mismatch', 'car-unknown')")

# What a sheet is for when nobody said. Written down here because the
# convention already existed in prose - `sheet_for` documented that a sheet
# stored before the question was asked is a race sheet - and v8 turned it into
# a NOT NULL column with this default, so the string has to be one string.
DEFAULT_SHEET_PURPOSE = "race"


def _record_declared_constants(fields: dict) -> None:
    for value_key, source_key in _DECLARED_CONSTANTS.items():
        if value_key not in fields:
            continue
        if fields[value_key] is None:
            del fields[value_key]
            fields.setdefault(source_key, None)
        else:
            fields.setdefault(source_key, "declared")


class Store:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        # **Three settings that cost nothing to be wrong about, left at
        # defaults sized for a phone.** This database is 178 MB and 99% of it
        # is one table of 481 KB telemetry blobs; the default 2 MB page cache
        # holds about four of them, so a sweep re-reads almost everything from
        # disk every time. Measured on a copy: a whole-table blob sweep falls
        # from 199.9 ms to 116.5 ms with the cache and a memory map.
        #
        # None of these three trade durability. `synchronous` does, and is
        # deliberately NOT set here: under WAL, NORMAL keeps everything safe
        # across an app crash and risks only the last commits in a power cut,
        # which is the usual setting for a local single-user app - but it is
        # the driver's race data and his call, not one to make silently in a
        # performance pass. It is worth about 1 ms per lap write.
        self._conn.execute("PRAGMA cache_size = -65536")     # 64 MB, not 2
        self._conn.execute("PRAGMA temp_store = MEMORY")
        self._conn.execute("PRAGMA mmap_size = 268435456")   # 256 MB
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        """Create or upgrade the schema.

        An older file is upgraded in place, in three passes: the script creates
        whatever tables are missing, `ADDED_COLUMNS` adds columns to tables
        that already existed, and then `MIGRATIONS` runs in version order for
        anything neither of those can express - a dropped column, a type
        change, a back-fill.  A *newer* file is refused rather than opened:
        this build would not know about its columns, and quietly writing to it
        is how data gets lost.

        The whole upgrade is one transaction.  A migration that raises rolls
        the file back to the version it opened at rather than leaving it
        half-converted, which is the state nothing else in the app could read.

        **Foreign keys are off for the upgrade and checked afterwards.**
        Altering a UNIQUE constraint in sqlite means rebuilding the table -
        v8 has to, because a constraint is an implicit index that `DROP INDEX`
        cannot reach - and `DROP TABLE` on a parent with foreign keys on runs
        an implicit `DELETE FROM` that trips the constraint. `PRAGMA
        foreign_keys` is a **no-op inside a transaction**, so the toggle has to
        live out here rather than in the migration that needs it. Nothing is
        taken on trust: `foreign_key_check` runs before the keys go back on,
        and a reference that did not survive is raised rather than logged.
        """
        self._conn.execute("PRAGMA foreign_keys = OFF")
        try:
            self._upgrade()
            broken = self._conn.execute("PRAGMA foreign_key_check").fetchall()
            if broken:
                raise RuntimeError(
                    f"{self.path}: the schema upgrade left {len(broken)} "
                    f"dangling reference(s): {broken[:5]}")
        finally:
            self._conn.execute("PRAGMA foreign_keys = ON")

    def _upgrade(self) -> None:
        with self._write() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"{self.path} is schema v{version}, this build expects "
                    f"v{SCHEMA_VERSION}. Point at a different file or migrate."
                )
            conn.executescript(DDL)
            for table, columns in ADDED_COLUMNS.items():
                existing = {row["name"] for row in
                            conn.execute(f"PRAGMA table_info({table})")}
                for name, kind in columns:
                    if name not in existing:
                        conn.execute(
                            f"ALTER TABLE {table} ADD COLUMN {name} {kind}")

            for target in sorted(MIGRATIONS):
                if target <= version:
                    continue
                label, migrate = MIGRATIONS[target]
                migrate(conn)
                log("store").info("migrated %s to v%s (%s)",
                                  self.path, target, label)

            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            with self._conn:
                yield self._conn

    def _query(self, sql: str, params: Sequence = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------- app state

    def set_state(self, key: str, value: str | int | None) -> None:
        with self._write() as conn:
            if value is None:
                conn.execute("DELETE FROM app_state WHERE key = ?", (key,))
            else:
                conn.execute(
                    "INSERT INTO app_state (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)))

    def get_state(self, key: str) -> str | None:
        rows = self._query("SELECT value FROM app_state WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def custom_catalog(self, kind: str) -> list[str]:
        """Names the driver added because the shipped list was missing them."""
        raw = self.get_state(f"custom_{kind}s")
        return json.loads(raw) if raw else []

    def add_to_catalog(self, kind: str, name: str) -> None:
        names = self.custom_catalog(kind)
        if name and name not in names:
            names.append(name)
            self.set_state(f"custom_{kind}s", json.dumps(sorted(names)))

    def active_event_id(self) -> int | None:
        raw = self.get_state("active_event_id")
        if raw is None:
            return None
        # The event may have been deleted since; an id pointing at nothing is
        # worse than no id at all.
        event_id = int(raw)
        return event_id if self.get_event(event_id) else None

    # ---------------------------------------------------------------- events

    def create_event(self, **fields) -> int:
        fields.setdefault("created_at", _now())
        _record_declared_constants(fields)
        fields["updated_at"] = _now()
        for key in ("available_compounds", "required_compounds"):
            if isinstance(fields.get(key), (list, tuple)):
                fields[key] = json.dumps(list(fields[key]))
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self._write() as conn:
            cur = conn.execute(
                f"INSERT INTO events ({cols}) VALUES ({marks})", list(fields.values()))
            event_id = int(cur.lastrowid)
            self._key_event(conn, event_id)
            return event_id

    def update_event(self, event_id: int, **fields) -> None:
        if not fields:
            return
        _record_declared_constants(fields)
        if not fields:
            return
        # `record_measured_clock` refuses to write over a typed figure, but nothing
        # ever moved `clock_source` back off "measured" - so once the app had measured
        # the clock once, the driver's later correction was stored and then quietly
        # replaced by the next session's reading.  Writing either half of the pair from
        # the form re-declares it.  Only an actual change counts: a no-op re-save of a
        # measured event must not throw the measurement away.
        clock = ("start_hour", "time_multiplier")
        if any(key in fields for key in clock):
            current = self.get_event(event_id)
            if current is not None and "clock_source" in current and any(
                    fields[key] != current[key] for key in clock if key in fields):
                fields.setdefault("clock_source", "typed")
        fields["updated_at"] = _now()
        for key in ("available_compounds", "required_compounds"):
            if isinstance(fields.get(key), (list, tuple)):
                fields[key] = json.dumps(list(fields[key]))
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self._write() as conn:
            conn.execute(f"UPDATE events SET {assignments} WHERE id = ?",
                         [*fields.values(), event_id])
            # Re-key whenever the declaration moved. A track edited from Monza
            # to Suzuka with `layout_id` still pointing at Monza's Full Course
            # is the same class of drift this whole change exists to remove.
            if any(k in fields for k in ("track", "layout", "car_name")):
                self._key_event(conn, event_id, rekey=True)

    def _key_event(self, conn: sqlite3.Connection, event_id: int,
                   *, rekey: bool = False) -> None:
        """Resolve an event's declared car and circuit to canonical rows.

        **Resolution, not enforcement.** Refusing a write that cannot resolve
        is stage 4's job and belongs with the repair screen that would let the
        driver do something about it; until then an unresolvable event is
        flagged `quarantined` and keeps everything it has. Losing a saved
        event because the catalogue was read before GT7 shipped a car is
        exactly the loss the driver said must not happen.
        """
        from pitcrew.store.identity import IDENTITY_OK, IDENTITY_QUARANTINED

        row = conn.execute(
            "SELECT track, layout, car_name, car_ref, layout_id FROM events "
            "WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return
        car_ref = None if rekey else row["car_ref"]
        layout_id = None if rekey else row["layout_id"]

        if car_ref is None and row["car_name"]:
            found = conn.execute("SELECT id FROM cars WHERE name = ? "
                                 "AND status = 'canonical'",
                                 (row["car_name"],)).fetchone()
            car_ref = int(found["id"]) if found else None
        if layout_id is None and row["track"] and row["layout"]:
            found = conn.execute(
                "SELECT tl.id FROM track_layouts tl JOIN tracks t "
                "ON t.id = tl.track_id WHERE t.name = ? AND tl.layout = ? "
                "AND tl.status = 'canonical'",
                (row["track"], row["layout"])).fetchone()
            layout_id = int(found["id"]) if found else None

        resolved = car_ref is not None and layout_id is not None
        conn.execute(
            "UPDATE events SET car_ref = ?, layout_id = ?, identity_status = ? "
            "WHERE id = ?",
            (car_ref, layout_id,
             IDENTITY_OK if resolved else IDENTITY_QUARANTINED, event_id))

    def get_event(self, event_id: int) -> dict | None:
        rows = self._query("SELECT * FROM events WHERE id = ?", (event_id,))
        return _event_row(rows[0]) if rows else None

    def list_events(self) -> list[dict]:
        # id breaks the tie: timestamps are second-resolution, so two events
        # created in the same second would otherwise come back in any order.
        rows = self._query("SELECT * FROM events ORDER BY updated_at DESC, id DESC")
        return [_event_row(r) for r in rows]

    def delete_event(self, event_id: int) -> None:
        with self._write() as conn:
            conn.execute("DELETE FROM events WHERE id = ?", (event_id,))

    # ------------------------------------------------- canonical identity (v7)
    #
    # `cars` and `track_layouts` are the only places a car or a circuit has a
    # stable identifier. Everything here reads the stored `slug` column; no
    # method in this section composes a key, and no caller should either.

    def list_cars(self, *, include_quarantined: bool = False) -> list[dict]:
        """Every car that may be selected, in name order.

        Quarantined rows are absent by default and that is the point: a car
        auto-created from an id nothing recognised exists, holds its session's
        data and is offered to nobody until the driver merges it to a real
        name.
        """
        clause = "" if include_quarantined else "WHERE status = 'canonical'"
        return [dict(r) for r in self._query(
            f"SELECT * FROM cars {clause} ORDER BY name")]

    def get_car(self, car_ref: int) -> dict | None:
        rows = self._query("SELECT * FROM cars WHERE id = ?", (car_ref,))
        return dict(rows[0]) if rows else None

    def car_by_name(self, name: str | None) -> dict | None:
        if not name:
            return None
        rows = self._query("SELECT * FROM cars WHERE name = ?", (name,))
        return dict(rows[0]) if rows else None

    def car_by_gt7_id(self, gt7_car_id: int | None) -> dict | None:
        """The car the game's own id belongs to, or None if nothing claims it.

        None is the interesting answer: it is a car the catalogue has never
        heard of, and the session that produced it must still record in full.
        """
        if gt7_car_id is None:
            return None
        rows = self._query("SELECT * FROM cars WHERE gt7_car_id = ?",
                           (int(gt7_car_id),))
        return dict(rows[0]) if rows else None

    def list_track_layouts(self, *, track: str | None = None,
                           include_quarantined: bool = False) -> list[dict]:
        where, params = [], []
        if not include_quarantined:
            where.append("tl.status = 'canonical'")
        if track is not None:
            where.append("t.name = ?")
            params.append(track)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        return [dict(r) for r in self._query(
            "SELECT tl.*, t.name AS track_name, t.slug AS track_slug "
            "FROM track_layouts tl JOIN tracks t ON t.id = tl.track_id "
            f"{clause} ORDER BY t.name, tl.id", params)]

    def get_track_layout(self, layout_id: int | None) -> dict | None:
        if layout_id is None:
            return None
        rows = self._query(
            "SELECT tl.*, t.name AS track_name, t.slug AS track_slug "
            "FROM track_layouts tl JOIN tracks t ON t.id = tl.track_id "
            "WHERE tl.id = ?", (layout_id,))
        return dict(rows[0]) if rows else None

    def log_identity_repair(self, *, table: str, row_id, field: str,
                            old_value=None, new_value=None, reason: str,
                            resolved_by: str) -> int:
        """Record one identity assignment the app derived, or the driver made."""
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO identity_repairs (table_name, row_id, field, "
                "old_value, new_value, reason, resolved_by, resolved_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (table, str(row_id), field,
                 None if old_value is None else str(old_value),
                 None if new_value is None else str(new_value),
                 reason, resolved_by, _now()))
            return int(cur.lastrowid)

    def list_identity_repairs(self, *, table: str | None = None) -> list[dict]:
        if table is None:
            return [dict(r) for r in self._query(
                "SELECT * FROM identity_repairs ORDER BY id")]
        return [dict(r) for r in self._query(
            "SELECT * FROM identity_repairs WHERE table_name = ? ORDER BY id",
            (table,))]

    def list_unresolved_identities(self) -> list[dict]:
        """Everything the driver has to answer, for the repair screen.

        Stage 4 builds the screen; this is the query it reads. It exists now
        because a quarantine nobody can see is indistinguishable from a
        deletion, and the whole justification for quarantining rather than
        dropping is that the row stays reachable.
        """
        out = [dict(r) for r in self._query(
            "SELECT 'event' AS scope, id, name AS label, identity_status "
            "FROM events WHERE COALESCE(identity_status, 'ok') != 'ok'")]
        out += [dict(r) for r in self._query(
            "SELECT 'session' AS scope, id, started_at AS label, "
            "identity_status FROM sessions "
            "WHERE COALESCE(identity_status, 'ok') NOT IN ('ok', 'no-reading')")]
        out += [dict(r) for r in self._query(
            "SELECT 'car' AS scope, id, name AS label, status AS identity_status "
            "FROM cars WHERE status = 'quarantined'")]
        return out

    # ----------------------------------------------------- setup (app state)

    def save_setup_sheet(self, sheet) -> int:
        """Insert or update a sheet by (car, name, **purpose**).  Returns its id.

        The purpose is in the conflict target because it is in the key, and it
        is in the key because it was not: the driver reported that loading a
        race sheet and then a qualifying sheet kept only the last one. It was
        not keeping the last one - it was overwriting the first and flipping
        its label, because `ON CONFLICT(car_name, sheet_name)` matched a sheet
        that answers a different question.

        `purpose` is normalised rather than allowed through as None. Sqlite
        counts two NULLs as distinct in a UNIQUE index, so an untagged sheet
        would stop matching its own row and accumulate a new one on every
        save - the same shape of bug in the opposite direction.
        """
        sheet.validate()
        purpose = (sheet.purpose or DEFAULT_SHEET_PURPOSE).strip()
        with self._write() as conn:
            conn.execute(
                "INSERT INTO setup_sheets (car_name, sheet_name, values_json, "
                "gears_json, shift_rpm_json, performance_json, build_json, "
                "notes, purpose, circuit_key, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(car_name, sheet_name, purpose) DO UPDATE SET "
                "values_json=excluded.values_json, gears_json=excluded.gears_json, "
                "shift_rpm_json=excluded.shift_rpm_json, "
                "performance_json=excluded.performance_json, "
                "build_json=excluded.build_json, notes=excluded.notes, "
                # **COALESCE, not excluded.** A save that does not know
                # the circuit must not erase one already established.
                "circuit_key=COALESCE(excluded.circuit_key, setup_sheets.circuit_key), "
                "updated_at=excluded.updated_at",
                (sheet.car_name, sheet.sheet_name, json.dumps(sheet.values),
                 json.dumps(sheet.gears),
                 # Keys are gear numbers; JSON turns them into strings and the
                 # reader turns them back, so a table never comes home keyed
                 # differently from how it went out.
                 json.dumps({str(g): r for g, r in (sheet.shift_rpm or {}).items()}),
                 json.dumps(sheet.performance),
                 json.dumps(sheet.build), sheet.notes, purpose,
                 sheet.circuit_key,
                 _now(), _now()))
            row = conn.execute(
                "SELECT id FROM setup_sheets WHERE car_name = ? "
                "AND sheet_name = ? AND purpose = ?",
                (sheet.car_name, sheet.sheet_name, purpose)).fetchone()
            return int(row["id"])

    def get_setup_sheet(self, sheet_id: int):
        rows = self._query("SELECT * FROM setup_sheets WHERE id = ?", (sheet_id,))
        return _setup_sheet(rows[0]) if rows else None

    def sheet_for(self, car_name: str, purpose: str,
                  circuit_key: str | None = None):
        """The car's most recent sheet for this purpose **at this circuit**.

        **None means none, and never another purpose's or another circuit's
        sheet.** A qualifying run measured against the race sheet files a
        symptom on a setup that was not on the car. The caller decides what to
        do about a missing sheet; substituting one here hides the question.

        Every sheet now carries a purpose - v8 made the column NOT NULL and
        back-filled the seven untagged rows to `race`, which is the convention
        this method already documented - so there is no null case left to
        interpret.

        **The circuit was missing from this key until 23 Aug 2026, and it cost
        five sessions.** Without it this returned the car's most recent race
        sheet whatever circuit he was at: a Road Atlanta session bound itself
        to "Yas Marina race Rev C", the export reported that as the setup as
        run, and its empty shift table silenced the beep for the session.

        `circuit_key=None` asks the old question - the most recent sheet for
        this car and purpose, circuit unexamined - and is kept for callers
        that genuinely have no circuit, such as listing what a car has ever
        run. **It is not what a session should ask.**

        A sheet whose own `circuit_key` is NULL never matches a named circuit.
        Missing is missing: a sheet that has never said which circuit it is
        for cannot be asserted to be for this one, and asserting it is exactly
        how the failure happened.
        """
        wanted = [sheet for sheet in self.list_setup_sheets(car_name)
                  if sheet.purpose == purpose
                  and (circuit_key is None
                       or sheet.circuit_key == circuit_key)]
        return wanted[0] if wanted else None

    def list_setup_sheets(self, car_name: str | None = None) -> list:
        # id breaks the tie: timestamps are second-resolution, so two sheets
        # saved in the same second come back in any order - and the caller
        # takes the first as "the current sheet", which then silently becomes
        # whichever one sqlite felt like.
        if car_name is None:
            rows = self._query(
                "SELECT * FROM setup_sheets ORDER BY updated_at DESC, id DESC")
        else:
            rows = self._query(
                "SELECT * FROM setup_sheets WHERE car_name = ? "
                "ORDER BY updated_at DESC, id DESC", (car_name,))
        return [_setup_sheet(r) for r in rows]

    def get_race_knowledge(self, circuit_key: str, event_id: int | None = None):
        """Ludo's briefing for this race, or None where nobody wrote one.

        **The event's own record wins over the circuit's FIELD BY FIELD, not
        row by row**, and the difference is a defect this shipped with for
        about an hour. The track constants - pit loss, the tow, the measured
        wear rates - are written once against the circuit with a null
        `event_id`; rival tendencies and the expected binding constraint belong
        to one race and are written against it. Taking the whole event row when
        one exists meant the first traffic pass to write rivals **shadowed
        every wear rate on that circuit**, and George silently went back to
        modelling wear.

        So the circuit record is the base and the event's non-null fields are
        laid over it. A field the event does not set is not a claim that the
        circuit's answer is wrong.

        None is a state George announces rather than one he papers over. See
        `race/knowledge.NO_NOTES`.
        """
        from dataclasses import fields, replace

        from pitcrew.race.knowledge import from_row

        rows = self._query(
            "SELECT * FROM race_knowledge WHERE circuit_key = ? "
            "AND (event_id = ? OR event_id IS NULL) "
            # NULLs last, so the event's own record is row zero when it exists.
            "ORDER BY event_id IS NULL, id DESC",
            (circuit_key, event_id))
        if not rows:
            return None

        specific = [from_row(row) for row in rows if row["event_id"] is not None]
        general = [from_row(row) for row in rows if row["event_id"] is None]
        if not specific:
            return general[0]
        if not general:
            return specific[0]

        over, base = specific[0], general[0]
        # `circuit_key` and `event_id` come from the overlay; everything else
        # is taken from it only where it has something to say.
        laid = {field.name: getattr(over, field.name)
                for field in fields(over)
                if field.name in ("circuit_key", "event_id")
                or getattr(over, field.name) not in (None, (), {}, "")}
        return replace(base, **laid)

    def save_race_knowledge(self, knowledge) -> int:
        """Write or replace one briefing. Validated before it is stored.

        **Refused rather than half-stored.** `calls_off` names calls George
        will not make, and a typo there is a call that quietly never happens -
        which is indistinguishable from an engineer who had nothing to say.
        `Knowledge.validate` is what catches it, and it runs here so no writer,
        including the MCP seam, can skip it.
        """
        import json

        knowledge.validate()
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO race_knowledge ("
                " circuit_key, event_id, pit_loss_s, refuel_l_per_s,"
                " undercut_s, overcut_s, expected_constraint, constraint_watch,"
                " rivals_json, tow_s_per_lap, calls_off_json, wear_rates_json,"
                " author, game_version, notes, written_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(circuit_key, event_id) DO UPDATE SET"
                "  pit_loss_s=excluded.pit_loss_s,"
                "  refuel_l_per_s=excluded.refuel_l_per_s,"
                "  undercut_s=excluded.undercut_s,"
                "  overcut_s=excluded.overcut_s,"
                "  expected_constraint=excluded.expected_constraint,"
                "  constraint_watch=excluded.constraint_watch,"
                "  rivals_json=excluded.rivals_json,"
                "  tow_s_per_lap=excluded.tow_s_per_lap,"
                "  calls_off_json=excluded.calls_off_json,"
                "  wear_rates_json=excluded.wear_rates_json,"
                "  author=excluded.author,"
                "  game_version=excluded.game_version,"
                "  notes=excluded.notes,"
                "  written_at=excluded.written_at",
                (knowledge.circuit_key, knowledge.event_id,
                 knowledge.pit_loss_s, knowledge.refuel_l_per_s,
                 knowledge.undercut_s, knowledge.overcut_s,
                 knowledge.expected_constraint, knowledge.constraint_watch,
                 json.dumps(list(knowledge.rivals)) if knowledge.rivals else None,
                 knowledge.tow_s_per_lap,
                 json.dumps(list(knowledge.calls_off)) if knowledge.calls_off else None,
                 json.dumps(knowledge.wear_rates) if knowledge.wear_rates else None,
                 knowledge.author, knowledge.game_version, knowledge.notes,
                 knowledge.written_at or _now()))
            return int(cur.lastrowid)

    def layout_length_m(self, circuit_key: str) -> float | None:
        """How long this circuit is, in metres, from the shipped catalogue.

        `track_layouts.slug` holds exactly the key `analysis/resolve
        .circuit_key` builds, so this is a lookup rather than a match.

        It is the anchor `analysis/distance.py` needs: `lap_distance_m` is
        integrated from speed and comes out 0.2-0.9% short on all three
        circuits with laps on file, which shifts every corner window in every
        export - and Ludo reads corner aggregates to build setups.
        """
        rows = self._query(
            "SELECT length_m FROM track_layouts WHERE slug = ?",
            (circuit_key,))
        length = rows[0]["length_m"] if rows else None
        return float(length) if length else None

    def sheet_filed_on(self, sheet_id: int) -> str | None:
        """When a sheet was last written into the app, as `YYYY-MM-DD`.

        **`SetupSheet` carries no timestamp and should not.** It is the sheet
        as a setup - values, gears, purpose, circuit - and a filing date is a
        fact about the record rather than about the car. But the record's date
        is exactly what `setup/doubt.py` needs: a revision document issued
        after it is one the app was never told about, which is the highest
        severity defect in the whole loop and the one nothing inside the app
        could see.

        The first draft of the doubt detector read `sheet.updated_at`, which
        does not exist, so `_sheet_date` returned `None` on every sheet and the
        detector was silent on all eight events - correct-looking, and dead.
        """
        rows = self._query(
            "SELECT COALESCE(updated_at, created_at) AS filed "
            "FROM setup_sheets WHERE id = ?", (sheet_id,))
        filed = rows[0]["filed"] if rows else None
        return str(filed)[:10] if filed else None

    def add_setup_change(self, session_id: int, change) -> int:
        change.validate()
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO setup_changes (session_id, from_lap, key, from_value, "
                "to_value, created_at) VALUES (?,?,?,?,?,?)",
                (session_id, change.from_lap, change.key, change.from_value,
                 change.to_value, _now()))
            return int(cur.lastrowid)

    def note_sheet_change(self, session_id: int) -> int:
        """Record what changed on the car since the last session like this one.

        **`setup_changes` had both ends built and no caller, and after 88
        sessions it held zero rows.** The charter calls that the single biggest
        gap in the system, because everything downstream of it is blocked:
        every change is an experiment, a regression cannot be recognised
        without knowing what moved, and setup history is not knowledge until a
        change is tied to the run that tested it.

        The caller was missing because the obvious one is impossible. The table
        is written as *mid-session* changes, and of the 23 setup values the
        only one the feed can see change mid-session is the gearbox - the other
        22 have no channel at all. So the mid-session case needs a human to
        type it and has no interface.

        **The between-session case needs neither, and it is the one that
        carries the experiment.** A session opens against a sheet; the last
        session on this car and circuit opened against another; the difference
        between them is exactly what this run is testing. Recorded at
        `from_lap=1`, which is what the column means - from lap one of this
        session, these values were different.

        Idempotent: a session that already has rows is left alone, so opening
        the same session twice cannot double the ledger.

        Returns the number of rows written. Silent when there is nothing to
        compare against - a first session on a car is not a change.
        """
        from pitcrew.setup.sheet import SetupChange

        rows = self._query(
            "SELECT s.setup_sheet_id, e.car_name FROM sessions s "
            "JOIN events e ON e.id = s.event_id WHERE s.id = ?", (session_id,))
        if not rows or not rows[0]["setup_sheet_id"]:
            return 0
        sheet_id, car_name = rows[0]["setup_sheet_id"], rows[0]["car_name"]
        if self._query("SELECT 1 FROM setup_changes WHERE session_id = ? "
                       "LIMIT 1", (session_id,)):
            return 0

        current = self.get_setup_sheet(sheet_id)
        if current is None:
            return 0
        # **The same circuit, or it is not a comparison.** A sheet built for
        # another track differs in every value that responds to the track, and
        # calling that an experiment would fill the ledger with noise - the
        # same error `tools/check_setup_sheets.py` was making one level up.
        previous = self._query(
            "SELECT sh.id FROM sessions s "
            "JOIN events e ON e.id = s.event_id "
            "JOIN setup_sheets sh ON sh.id = s.setup_sheet_id "
            "WHERE s.id < ? AND e.car_name = ? AND sh.purpose = ? "
            "AND sh.circuit_key IS ? AND sh.id != ? "
            "ORDER BY s.id DESC LIMIT 1",
            (session_id, car_name, current.purpose, current.circuit_key,
             sheet_id))
        if not previous:
            return 0
        before = self.get_setup_sheet(previous[0]["id"])
        if before is None:
            return 0

        written = 0
        for key in sorted(set(current.values) | set(before.values)):
            was, now = before.values.get(key), current.values.get(key)
            if was is None and now is None:
                continue
            if was is not None and now is not None and abs(was - now) <= 1e-9:
                continue
            try:
                self.add_setup_change(
                    session_id,
                    SetupChange(from_lap=1, key=key,
                                from_value=was, to_value=now))
            except Exception:                          # noqa: BLE001
                # A key outside the shared vocabulary is a sheet problem, not a
                # reason to lose the rest of the ledger. `SetupChange.validate`
                # has already refused it and said why.
                continue
            written += 1
        if written:
            log("store").info(
                "session %s opens with %s value(s) changed from %r - filed as "
                "this run's experiment", session_id, written, before.sheet_name)
        return written

    def list_setup_changes(self, session_id: int) -> list:
        from pitcrew.setup.sheet import SetupChange
        rows = self._query(
            "SELECT * FROM setup_changes WHERE session_id = ? ORDER BY from_lap, id",
            (session_id,))
        return [SetupChange(from_lap=r["from_lap"], key=r["key"],
                            from_value=r["from_value"], to_value=r["to_value"])
                for r in rows]

    def log_radio(self, session_id: int | None, *, heard: str, said: str,
                  lap_num: int | None = None, intent: str | None = None,
                  action: str | None = None, distance: float | None = None,
                  reason: str | None = None) -> None:
        """Record one push-to-talk exchange, both sides.

        **Never raises into the caller.** This is written from the answer
        callback while the driver is on track, and a database hiccup must not
        cost him the reply he already heard.

        `action`, `distance` and `reason` are the gate's own verdict. They are
        optional because a caller that does not have one should write null
        rather than a plausible substitute - the whole reason these columns
        exist is that a re-derived intent was standing in for a real decision.
        """
        try:
            with self._write() as conn:
                conn.execute(
                    "INSERT INTO radio (session_id, lap_num, heard, said, "
                    "intent, action, distance, reason, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (session_id, lap_num, heard, said, intent, action,
                     distance, reason, _now()))
        except sqlite3.Error:
            log("store").exception("radio exchange not recorded")

    def list_radio(self, session_id: int) -> list[dict]:
        return [dict(r) for r in self._query(
            "SELECT * FROM radio WHERE session_id = ? ORDER BY id",
            (session_id,))]

    def event_radio(self, event_id: int) -> list[dict]:
        """Every exchange across the event's sessions, oldest first."""
        return [dict(r) for r in self._query(
            "SELECT radio.*, sessions.kind AS session_kind "
            "FROM radio JOIN sessions ON sessions.id = radio.session_id "
            "WHERE sessions.event_id = ? ORDER BY radio.id", (event_id,))]

    def save_range_record(self, record) -> None:
        record.validate()
        with self._write() as conn:
            conn.execute(
                "INSERT INTO range_records (car_name, measured_date, game_version, "
                "verified, ranges_json, updated_at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(car_name) DO UPDATE SET "
                "measured_date=excluded.measured_date, "
                "game_version=excluded.game_version, verified=excluded.verified, "
                "ranges_json=excluded.ranges_json, updated_at=excluded.updated_at",
                (record.car_name, record.measured_date, record.game_version,
                 int(record.verified), json.dumps(record.ranges), _now()))

    def get_range_record(self, car_name: str):
        from pitcrew.setup.sheet import RangeRecord
        rows = self._query(
            "SELECT * FROM range_records WHERE car_name = ?", (car_name,))
        if not rows:
            return None
        row = rows[0]
        return RangeRecord(
            car_name=row["car_name"],
            measured_date=row["measured_date"],
            ranges=json.loads(row["ranges_json"]),
            game_version=row["game_version"],
            verified=bool(row["verified"]),
        )

    def cars_with_ranges(self) -> list[str]:
        rows = self._query("SELECT car_name FROM range_records ORDER BY car_name")
        return [r["car_name"] for r in rows]

    def seed_range_records(self, records) -> int:
        """Insert shipped range records for cars that have none yet.

        Ranges lived in a hand-edited JavaScript object literal in the tool
        this app replaced.  They are seeded once so nothing measured is lost,
        and then never again: a record in this table is something the driver
        read off the car's own settings screen, and shipped data must never
        overwrite it.
        """
        from pitcrew.setup.sheet import RangeRecord

        known = set(self.cars_with_ranges())
        seeded = 0
        for record in records:
            car = record.get("car")
            if not car or car in known:
                continue
            self.save_range_record(RangeRecord(
                car_name=car,
                measured_date=record.get("measuredDate") or "",
                ranges={k: list(v) for k, v in (record.get("r") or {}).items()},
                game_version=record.get("gameVersion"),
                verified=bool(record.get("verified")),
            ))
            seeded += 1
        return seeded

    # ------------------------------------------------------------- prompt log

    def log_prompt(self, *, kind: str, body: str, prompt_version: str,
                   app_version: str, event_id: int | None = None,
                   session_id: int | None = None, car_name: str | None = None,
                   circuit: str | None = None) -> int:
        """Record a prompt as issued.  Advice that is never recorded cannot be
        audited, and a returned sheet has to be traceable to the template that
        asked for it."""
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO prompt_issues (event_id, session_id, kind, "
                "car_name, circuit, prompt_version, app_version, body, "
                "issued_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (event_id, session_id, kind, car_name, circuit, prompt_version,
                 app_version, body, _now()))
            return int(cur.lastrowid)

    def save_prompt_reply(self, issue_id: int, reply: str | None) -> None:
        """Store what the knowledge base sent back, against the prompt that
        asked for it.  Not parsed - the setup values re-enter the app through
        the Event screen's paste box, unchanged."""
        with self._write() as conn:
            conn.execute(
                "UPDATE prompt_issues SET reply = ?, replied_at = ? WHERE id = ?",
                (reply or None, _now() if reply else None, issue_id))

    def list_prompts(self, event_id: int | None = None,
                     limit: int = 50) -> list[dict]:
        if event_id is None:
            rows = self._query(
                "SELECT * FROM prompt_issues ORDER BY issued_at DESC, id DESC "
                "LIMIT ?", (limit,))
        else:
            rows = self._query(
                "SELECT * FROM prompt_issues WHERE event_id = ? "
                "ORDER BY issued_at DESC, id DESC LIMIT ?", (event_id, limit))
        return [dict(r) for r in rows]

    def get_prompt(self, issue_id: int) -> dict | None:
        rows = self._query("SELECT * FROM prompt_issues WHERE id = ?",
                           (issue_id,))
        return dict(rows[0]) if rows else None

    # -------------------------------------------------------------- sessions

    def start_session(self, event_id: int, kind: str,
                      tune_label: str | None = None,
                      setup_sheet_id: int | None = None,
                      practice_mode: str | None = None,
                      practice_intent: str | None = None,
                      rehearsal: bool = False,
                      game_version: str | None = None) -> int:
        from pitcrew.store.identity import IDENTITY_OK

        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (event_id, kind, tune_label, setup_sheet_id, "
                "practice_mode, practice_intent, rehearsal, game_version, "
                "identity_status, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, kind, tune_label, setup_sheet_id, practice_mode,
                 practice_intent, int(rehearsal),
                 # **Stamped now, at the moment of recording, and never
                 # inferred later.** An empty setting stores NULL rather than a
                 # guess: the export refuses a payload with no version, which
                 # is the loud failure. A version filled in afterwards from
                 # whatever happens to be installed is the quiet one.
                 (game_version or "").strip() or None,
                 # A session opens carrying the event's declaration. Only the
                 # stream can contradict it, and until a packet lands there is
                 # nothing to contradict it with - opening at anything else
                 # would accuse a run of being the wrong car before it has
                 # turned a wheel, and would hide every session recorded with
                 # GT7 switched off.
                 IDENTITY_OK, _now()))
            return int(cur.lastrowid)

    def record_measured_clock(self, event_id: int, start_hour: float | None,
                              multiplier: float | None) -> bool:
        """Write back what the game clock turned out to be, if he has not said.

        **Never over a typed value.** His declaration is primary evidence and
        the measurement is corroboration; a measurement that quietly replaced
        a declaration would destroy the disagreement between them, which is
        the finding worth more than either.

        Returns whether anything was written, so the caller can say so.
        """
        if start_hour is None and multiplier is None:
            return False
        row = self.get_event(event_id)
        if row is None:
            return False
        source = row["clock_source"] if "clock_source" in row.keys() else None
        typed = (row["start_hour"] is not None
                 or row["time_multiplier"] is not None)
        if typed and source != "measured":
            return False
        with self._write() as conn:
            conn.execute(
                "UPDATE events SET start_hour = ?, time_multiplier = ?, "
                "clock_source = 'measured', updated_at = ? WHERE id = ?",
                (start_hour, multiplier, _now(), event_id))
        return True

    def set_session_sheet(self, session_id: int, sheet_id: int | None) -> None:
        """Correct which setup sheet a recorded session was run on.

        **The app could file a sheet and never re-attach one**, so a revision
        that arrived after a session was recorded left that session pointing at
        the older sheet - or, where no sheet for the purpose existed at all, at
        nothing. Both were then presented as the setup as run.

        This is a repair, not a workflow: the session already happened and only
        the driver knows what was in the car. Nothing in the app calls it
        automatically, and nothing should.
        """
        with self._write() as conn:
            conn.execute("UPDATE sessions SET setup_sheet_id = ? WHERE id = ?",
                         (sheet_id, session_id))

    def set_practice_intent(self, session_id: int, intent: str | None) -> None:
        """Say what this session was for, or unsay it."""
        with self._write() as conn:
            conn.execute(
                "UPDATE sessions SET practice_intent = ? WHERE id = ?",
                (intent, session_id))

    def set_practice_mode(self, session_id: int, mode: str | None) -> None:
        """Say which kind of session this was, or unsay it.

        Editable after the fact because it is only ever asked once, at the
        moment he is about to go out, and that is the worst time to make
        somebody answer a question carefully.
        """
        with self._write() as conn:
            conn.execute("UPDATE sessions SET practice_mode = ? WHERE id = ?",
                         (mode, session_id))

    def note_stream_facts(self, session_id: int, *, packet_format: str | None = None,
                          car_category: str | None = None,
                          fuel_capacity_l: float | None = None,
                          car_id: int | None = None,
                          wheelbase_m: float | None = None,
                          game_version: str | None = None) -> str | None:
        """Record what the stream actually delivered, once it is known.

        Returns the session's identity status where the car id moved it, so
        the caller can say so on screen while the run is happening.
        """
        with self._write() as conn:
            conn.execute(
                "UPDATE sessions SET packet_format = COALESCE(?, packet_format), "
                "car_category = COALESCE(?, car_category), "
                "fuel_capacity_l = COALESCE(?, fuel_capacity_l), "
                "wheelbase_m = COALESCE(?, wheelbase_m) WHERE id = ?",
                (packet_format, car_category, fuel_capacity_l, wheelbase_m,
                 session_id))
            if car_id is None:
                return None
            return self._observe_car_id(conn, session_id, int(car_id),
                                        game_version)

    def _observe_car_id(self, conn: sqlite3.Connection, session_id: int,
                        car_id: int, game_version: str | None) -> str | None:
        """Reconcile one observed packet car id against the event's declaration.

        **This is the gate bug 1 walked through.** Session 11 streamed a Gr.3
        class on an event whose car is a road car, and nothing in the app
        compared the two - so its lap 4 fuel burn became the approved race
        plan's `fuelPerLapL`. The comparison now happens while the run is
        happening, on the packet's own car id rather than on the class token,
        because a class is shared by dozens of cars and an id is not.

        Four outcomes, and none of them stops the session recording:

        * the event's car has no id yet - **learn it**, and note where from;
        * the id agrees - nothing to say;
        * the id belongs to a different known car - `car-mismatch`, which the
          archive already had **two** of and not one (sessions 11 and 5), so
          this is a class of defect rather than an incident;
        * the id belongs to nothing on file - a **quarantined** car row is
          created for it so the session has a distinct id immediately. Not
          selectable, not pooled into any fit, not lost.
        """
        from pitcrew.store.identity import (
            IDENTITY_NO_READING,
            IDENTITY_OK,
            STATUS_QUARANTINED,
            car_slug,
            reconcile_car_id,
            unknown_car_name,
        )

        event_car = conn.execute(
            "SELECT c.* FROM sessions s JOIN events e ON e.id = s.event_id "
            "JOIN cars c ON c.id = e.car_ref WHERE s.id = ?",
            (session_id,)).fetchone()
        owner = conn.execute("SELECT * FROM cars WHERE gt7_car_id = ?",
                             (car_id,)).fetchone()
        outcome = reconcile_car_id(car_id, event_car=event_car,
                                   car_by_gt7_id=owner)

        if outcome.status == IDENTITY_NO_READING:
            # 0 is "the car has not loaded", not a car. Nothing is written and
            # nothing is accused; a later packet with a real id resolves it.
            current = conn.execute(
                "SELECT identity_status FROM sessions WHERE id = ?",
                (session_id,)).fetchone()
            return current["identity_status"] if current else None

        car_ref_observed = outcome.car_ref_observed

        if outcome.learn_gt7_id_for is not None:
            conn.execute(
                "UPDATE cars SET gt7_car_id = ?, gt7_id_source = "
                "'observed-on-stream', gt7_id_game_version = ? WHERE id = ?",
                (car_id, game_version, outcome.learn_gt7_id_for))
            conn.execute(
                "INSERT INTO identity_repairs (table_name, row_id, field, "
                "old_value, new_value, reason, resolved_by, resolved_at) "
                "VALUES ('cars',?,'gt7_car_id',NULL,?,?,'observed-on-stream',?)",
                (str(outcome.learn_gt7_id_for), str(car_id),
                 f"first seen driving in session {session_id}", _now()))

        if outcome.create_quarantined_id is not None:
            # The slug comes off the name through the one slug function, even
            # here where the name is generated and the answer is obvious. A
            # second way of composing a key is how all three of these bugs
            # started.
            name = unknown_car_name(car_id)
            conn.execute(
                "INSERT OR IGNORE INTO cars (gt7_car_id, name, slug, "
                "gt7_id_source, gt7_id_game_version, status, created_at) "
                "VALUES (?,?,?,'observed-on-stream',?,?,?)",
                (car_id, name, car_slug(name), game_version,
                 STATUS_QUARANTINED, _now()))
            created = conn.execute("SELECT id FROM cars WHERE gt7_car_id = ?",
                                   (car_id,)).fetchone()
            car_ref_observed = int(created["id"]) if created else None
            conn.execute(
                "INSERT INTO identity_repairs (table_name, row_id, field, "
                "old_value, new_value, reason, resolved_by, resolved_at) "
                "VALUES ('cars',?,'status',NULL,?,?,'observed-on-stream',?)",
                (str(car_ref_observed), STATUS_QUARANTINED,
                 outcome.note or "unknown car id on the wire", _now()))

        conn.execute(
            "UPDATE sessions SET car_id_observed = ?, car_ref_observed = ?, "
            "identity_status = ? WHERE id = ?",
            (car_id, car_ref_observed, outcome.status, session_id))

        if outcome.status != IDENTITY_OK:
            log("store").warning("session %s identity is %s: %s", session_id,
                                 outcome.status, outcome.note)
            conn.execute(
                "INSERT INTO identity_repairs (table_name, row_id, field, "
                "old_value, new_value, reason, resolved_by, resolved_at) "
                "VALUES ('sessions',?,'identity_status',?,?,?, "
                "'observed-on-stream',?)",
                (str(session_id), IDENTITY_OK, outcome.status,
                 outcome.note or "", _now()))
        return outcome.status

    def set_session_video(self, session_id: int, *, path: str | None,
                          started_at: str | None) -> None:
        """Where this session's capture is, and the wall clock at its second 0.

        **Written only when the app itself started the recording.** A capture
        made by hand has no zero the app can know, and inventing one would put
        every seek in `race/video_index.py` minutes out while reading as exact.
        """
        with self._write() as conn:
            conn.execute(
                "UPDATE sessions SET video_path = ?, video_started_at = ? "
                "WHERE id = ?", (path, started_at, session_id))

    def end_session(self, session_id: int, *, at: str | None = None) -> None:
        """Close a session.  `at` is for closing one the app never got to
        close itself: stamping it now would claim it ran until the next
        launch, which could be days."""
        with self._write() as conn:
            conn.execute("UPDATE sessions SET ended_at = ? WHERE id = ?",
                         (at or _now(), session_id))

    def open_sessions(self) -> list[dict]:
        """Sessions with no end, newest first, each with its last sign of life.

        A session here means the app went without stopping.  `last_seen` is
        the last lap it stored, falling back to when it started - the honest
        answer to "how far did it get" when there is nothing else to go on.
        """
        rows = self._query(
            "SELECT sessions.*, "
            "  COALESCE(MAX(laps.recorded_at), sessions.started_at) AS last_seen "
            "FROM sessions LEFT JOIN laps ON laps.session_id = sessions.id "
            "WHERE sessions.ended_at IS NULL "
            "GROUP BY sessions.id ORDER BY sessions.started_at DESC")
        return [dict(r) for r in rows]

    def get_session(self, session_id: int) -> dict | None:
        rows = self._query("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return dict(rows[0]) if rows else None

    def list_sessions(self, event_id: int, kind: str | None = None) -> list[dict]:
        if kind is None:
            rows = self._query(
                "SELECT * FROM sessions WHERE event_id = ? ORDER BY started_at DESC",
                (event_id,))
        else:
            rows = self._query(
                "SELECT * FROM sessions WHERE event_id = ? AND kind = ? "
                "ORDER BY started_at DESC", (event_id, kind))
        return [dict(r) for r in rows]

    def delete_session(self, session_id: int) -> None:
        with self._write() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    # ------------------------------------------------------------------ laps

    def add_lap(self, session_id: int, lap, frames=None) -> int:
        """Store one completed lap and, if captured, its telemetry frames.

        `lap` is a `pitcrew.telemetry.session_state.Lap`; `frames` a
        `LapFrames`.  Both are written in one transaction so a lap never exists
        without the telemetry the export depends on.
        """
        with self._write() as conn:
            # **A plain INSERT, and it used to be INSERT OR REPLACE.**
            #
            # `laps` is UNIQUE(session_id, lap_num), and both `lap_frames`
            # and `grip_observations` reference `laps(id) ON DELETE CASCADE`
            # with `PRAGMA foreign_keys = ON`. A REPLACE on that constraint
            # is a DELETE followed by an INSERT, so it cascades. Reproduced
            # on a copy of the live database - one statement, one lap:
            #
            #     BEFORE  id=1    compound='RS'   frames=1  grip=7
            #     AFTER   id=364  compound=None   frames=0  grip=0
            #
            # It destroyed the raw 60 Hz blob, which is the one thing in this
            # database that cannot be recreated, took seven grip observations
            # with it, dropped the driver's own compound, and reissued the
            # lap id so that anything holding the old one now points at
            # nothing. It reported success.
            #
            # The failure modes are not comparable. A plain INSERT raises
            # `IntegrityError` on a collision, `controller.py` already
            # catches `sqlite3.Error` around this call and puts "Lap NOT
            # saved - the database rejected it" on the driver's screen. So
            # the choice is between a visible refusal and silent,
            # unrecoverable loss - and this app has had several lap-counting
            # regressions (a rolling start losing a lap, phantom fragment
            # laps, twenty-seven driven against twenty-six stored), any one
            # of which is what would deliver the collision.
            #
            # Not reachable today: `lap_num` is `len(self._laps) + 1` and
            # `_laps` is only ever appended to, and every `bridge.reset()` is
            # followed by a `start_session()` with a fresh id. Changed
            # because "not reachable today" is not a property anyone can
            # keep, and the cost of being wrong about it is the telemetry.
            cur = conn.execute(
                "INSERT INTO laps "
                "(session_id, lap_num, lap_time_ms, delta_ms, fuel_start, fuel_end, "
                " fuel_used, position, compound, is_pit_lap, is_out_lap, gear_ratios, "
                " tyres_changed, fuel_added_l, tod_start_ms, tod_end_ms, "
                " standing_start_ms, crawl_s, off_track_s, spin_s, "
                " short_shift_rpm, laps_completed, race_elapsed_s, "
                " race_remaining_s, laps_dropped, recorded_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, lap.lap_num, lap.lap_time_ms, lap.delta_ms,
                 lap.fuel_start, lap.fuel_end, lap.fuel_used, lap.position,
                 lap.compound, int(lap.is_pit_lap), int(lap.is_out_lap),
                 json.dumps(lap.gear_ratios) if lap.gear_ratios else None,
                 # None stays None. A lap with no stop makes no claim about
                 # the tyres, and `0` would be the claim that they stayed on.
                 (None if getattr(lap, "tyres_changed", None) is None
                  else int(lap.tyres_changed)),
                 getattr(lap, "fuel_added_l", None),
                 frames.tod_start_ms if frames is not None else None,
                 frames.tod_end_ms if frames is not None else None,
                 frames.standing_start_ms if frames is not None else None,
                 getattr(frames, "crawl_s", None) if frames is not None else None,
                 getattr(frames, "off_track_s", None) if frames is not None else None,
                 getattr(frames, "spin_s", None) if frames is not None else None,
                 # None stays None: a lap recorded before this existed makes
                 # no claim about how it was driven, and 0.0 would be the
                 # claim that it was driven on the normal threshold.
                 getattr(lap, "short_shift_rpm", None),
                 getattr(lap, "laps_completed", None),
                 # **The clock as it read at this crossing.** Carried on the
                 # Lap because that is the only thing that reaches here, and
                 # the whole point is that a post-race audit can compare the
                 # app's answer against GT7's `laps_completed` beside it.
                 getattr(lap, "race_elapsed_s", None),
                 getattr(lap, "race_remaining_s", None),
                 getattr(lap, "laps_dropped", None),
                 _now()))
            # **The declared fuel map, because no channel carries it.** It was
            # null on every lap of every session ever recorded - the cheapest
            # field on the sheet, and the whole fuel model is expressed per
            # map. It is a property of how the round is being driven rather
            # than of the lap, so it comes off the event; NULL where nobody
            # has declared one, never a plausible 1.
            conn.execute(
                "UPDATE laps SET fuel_map = COALESCE(?, ("
                "  SELECT e.fuel_map FROM events e JOIN sessions s "
                "  ON s.event_id = e.id WHERE s.id = ?)) "
                "WHERE id = ? AND fuel_map IS NULL",
                (getattr(lap, "fuel_map", None), session_id,
                 int(cur.lastrowid)))
            lap_id = int(cur.lastrowid)
            if frames is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO lap_frames "
                    "(lap_id, sample_hz, frame_count, blob) VALUES (?,?,?,?)",
                    (lap_id, frames.sample_hz, frames.frame_count, frames.blob))
                self._note_top_speed(conn, session_id, frames)
            return lap_id

    # The fastest a frame has ever gone at this event. Ratcheted up only, and
    # only off a lap that was actually completed - a max taken from live
    # packets would include the garage, the replay and anything the stream
    # showed while nobody was driving.
    #
    # 500 km/h is the sanity bound. `analysis/grip` records that the speed
    # channel drops to exactly 0.0 for runs of frames mid-straight, which a
    # maximum is immune to; a spike upward is not, and one bad frame would
    # move a divisor every lap of every future session at this circuit.
    MAX_PLAUSIBLE_KPH = 500.0

    def _note_top_speed(self, conn: sqlite3.Connection, session_id: int,
                        frames) -> None:
        """Ratchet the event's reference speed up, if this lap beat it.

        **The value arrives on `frames` now; this used to decode the blob to
        find it.** `decode_frames(blob)` on the lap that had just been
        encoded three lines earlier cost 40.2 ms, of which about 30 ms was
        `json.loads` holding the GIL uninterruptibly - on the Qt thread, at
        every lap crossing, while the audio callback needs the GIL a hundred
        times a second. `LapRecorder.encode` takes the same maximum off the
        uncompressed rows for 0.369 ms, which is the pattern `crawl_s`,
        `off_track_s` and `spin_s` already follow.

        A lap stored without the field - an older `LapFrames`, or a caller
        passing its own object - simply does not move the reference, which is
        the right failure: the ratchet only ever goes up, so a missed lap
        costs nothing that the next one will not supply.
        """
        top = getattr(frames, "top_kph", None)
        if top is None or not 0.0 < top < self.MAX_PLAUSIBLE_KPH:
            return
        conn.execute(
            "UPDATE events SET observed_top_kph = MAX(?, "
            "COALESCE(observed_top_kph, 0)) WHERE id = "
            "(SELECT event_id FROM sessions WHERE id = ?)",
            (round(top, 1), session_id))

    def list_laps(self, session_id: int) -> list[dict]:
        rows = self._query(
            "SELECT * FROM laps WHERE session_id = ? ORDER BY lap_num", (session_id,))
        return [dict(r) for r in rows]

    def list_evidence_laps(self, event_id: int) -> list[dict]:
        """Every lap that says something about how this event will go.

        Practice, rehearsals, **and the league race itself**. The driver's
        instruction, in as many words: *"race fuel and pace should be included
        from race sims and actual race data too - it all combines with
        practice session data for the full picture."*

        This used to stop at `kind = 'practice' OR rehearsal = 1`, on the
        argument that the race is the thing being planned for and a plan built
        on the race it is planning is not a plan. **That argument protects
        against a circularity that does not happen here**: the in-race
        re-planner reads `RaceInputs` captured once at arming and never
        rebuilds them, so a race can never be costed on its own laps while it
        is being run. What the exclusion actually did was throw away the best
        evidence in the database the moment it was gathered.

        And it is the best evidence, on every channel:

        * **Wear.** CLAUDE.md §5.2 wants `w` measured "at the multiplier
          actually being raced, from a run at genuine race pace from a full
          tank" - which is a description of a race stint and not of a practice
          one. The Monza race of 18 Aug 2026 read 0.056/lap against a model
          that said 0.04412, and the model's stint limit was four laps long.
        * **Fuel.** Race pace, race fuel map, real traffic, real defending.
        * **Pace.** The same, and the achieved-lap figure a timed race's
          distance rests on is explicitly meant to be laps as they were
          actually driven.

        **What keeps a race honest is `LapInput.counted`, not this predicate.**
        It already drops out-laps, in-laps, anything the driver struck, and any
        lap with an incident in it - which is exactly the difference between a
        race lap and a practice lap, and it was always applied to both. On
        session 52 that removes the pit lap and leaves the twenty-five green
        ones. Recency weighting does the rest: a race is the most recent
        session by construction, so it leads the picture it joins without
        being the only thing in it.

        **And no laps whose car the stream contradicted.** This is the gate
        that closes bug 1. On 17 Aug 2026 session 11 was found carrying
        `car_category='GR3'` on event 2, whose car is a road car GT7 streams
        as `GR.N`. This query scoped on `event_id` alone - no car predicate
        anywhere - so its lap 4 burn of 7.563377380371094 L became
        `assumptions.fuelPerLapL = 7.563` in the **approved** race plan. The
        plan was not influenced by the wrong car's session; that one lap was
        the figure.

        The predicate is on the identity, not on the class: two Gr.3 cars
        share a class and do not share an id, so filtering on
        `car_category` would still have let the wrong Gr.3 car through.

        `EVIDENCE_IDENTITY_SQL` states which statuses disqualify and why - the
        short version is that a contradiction does and an absent reading does
        not. `COALESCE` so that a row written before the column existed is not
        accused of anything: missing is null, and null is not a mismatch.

        **Excluded is not lost.** Every one of session 11's laps and frames
        reads back in full through `list_laps` and `list_event_laps`, and the
        export still describes them. They just do not cost a race plan.
        """
        rows = self._query(
            "SELECT laps.*, sessions.started_at AS session_started, "
            "       sessions.practice_mode AS practice_mode, "
            "       sessions.practice_intent AS practice_intent, "
            "       sessions.setup_sheet_id AS setup_sheet_id, "
            # **Which physics produced this lap.** 1.71 reworked the
            # tyre model, so a lap either side of it is not evidence
            # about the same car - see `analysis/version`.
            "       sessions.game_version AS game_version, "
            "       sessions.kind AS session_kind, "
            "       COALESCE(sessions.rehearsal, 0) AS rehearsal "
            "FROM laps JOIN sessions ON sessions.id = laps.session_id "
            "WHERE sessions.event_id = ? "
            f"  AND {EVIDENCE_IDENTITY_SQL} "
            "ORDER BY sessions.started_at, sessions.id, laps.lap_num",
            (event_id,))
        return [dict(r) for r in rows]

    def excluded_evidence_sessions(self, event_id: int) -> list[dict]:
        """Sessions this event has that no plan may be built on, and why.

        The counterpart to the gate above: a session held out of the evidence
        set silently is the same failure as one wrongly let in. The strategy
        screen names these so the driver can see what his plan is *not* costed
        on, and the repair screen can act on them.
        """
        return [dict(r) for r in self._query(
            "SELECT sessions.*, COUNT(laps.id) AS lap_count "
            "FROM sessions LEFT JOIN laps ON laps.session_id = sessions.id "
            "WHERE sessions.event_id = ? "
            f"  AND NOT ({EVIDENCE_IDENTITY_SQL}) "
            "GROUP BY sessions.id ORDER BY sessions.started_at, sessions.id",
            (event_id,))]

    def list_event_laps(self, event_id: int, kind: str = "practice") -> list[dict]:
        rows = self._query(
            "SELECT laps.*, sessions.started_at AS session_started, "
            "       sessions.practice_mode AS practice_mode, "
            "       sessions.practice_intent AS practice_intent, "
            "       sessions.setup_sheet_id AS setup_sheet_id, "
            # **Which physics produced this lap.** 1.71 reworked the
            # tyre model, so a lap either side of it is not evidence
            # about the same car - see `analysis/version`.
            "       sessions.game_version AS game_version, "
            "       sessions.kind AS session_kind, "
            "       COALESCE(sessions.rehearsal, 0) AS rehearsal "
            "FROM laps JOIN sessions ON sessions.id = laps.session_id "
            "WHERE sessions.event_id = ? AND sessions.kind = ? "
            # `started_at` is second-resolution, so two runs begun in the same
            # second tie and their laps interleave - which reads as one run
            # whose tank refills every other lap. The session id breaks the tie
            # in the order the runs actually happened.
            "ORDER BY sessions.started_at, sessions.id, laps.lap_num",
            (event_id, kind))
        return [dict(r) for r in rows]

    # Columns `set_lap_flags` is allowed to touch. A whitelist rather than a
    # free-form update because the caller builds the column names, and the one
    # caller is a tool that rewrites laps in bulk.
    LAP_FLAGS = ("is_pit_lap", "is_out_lap", "tyres_changed", "fuel_added_l")

    def set_lap_flags(self, lap_id: int, **values) -> None:
        """Set what re-reading a stored lap's frames found.

        Kept apart from the per-mark setters above because this writes what the
        *app* worked out, in bulk, over sessions recorded before it could work
        it out. Nothing the driver entered is reachable from here.
        """
        unknown = set(values) - set(self.LAP_FLAGS)
        if unknown:
            raise ValueError(f"not a lap flag: {', '.join(sorted(unknown))}")
        if not values:
            return
        assignments = ", ".join(f"{name} = ?" for name in values)
        with self._write() as conn:
            conn.execute(f"UPDATE laps SET {assignments} WHERE id = ?",
                         (*values.values(), lap_id))

    def set_lap_compound(self, lap_id: int, compound: str | None) -> None:
        with self._write() as conn:
            conn.execute("UPDATE laps SET compound = ? WHERE id = ?", (compound, lap_id))

    def set_lap_tyres_fresh(self, lap_id: int, fresh: bool | None) -> None:
        """Record that this lap went out on a fresh set, or unsay it.

        None is not False. None is "he has not said", which is what every lap
        is until he does; False is the positive claim that the set carried over
        from the run before, which is worth as much and is his to make.
        """
        with self._write() as conn:
            conn.execute(
                "UPDATE laps SET tyres_fresh = ? WHERE id = ?",
                (None if fresh is None else int(fresh), lap_id))

    def set_lap_fuel_map(self, lap_id: int, fuel_map: int | None) -> None:
        with self._write() as conn:
            conn.execute("UPDATE laps SET fuel_map = ? WHERE id = ?", (fuel_map, lap_id))

    def exclude_lap(self, lap_id: int, reason: str | None) -> None:
        """Exclude a lap from the counted set, or re-include it with reason=None."""
        with self._write() as conn:
            conn.execute(
                "UPDATE laps SET excluded = ?, exclusion_reason = ? WHERE id = ?",
                (0 if reason is None else 1, reason, lap_id))

    def set_lap_wear(self, lap_id: int, fl: float | None, fr: float | None,
                     rl: float | None, rr: float | None, *,
                     source: str = WEAR_DRIVER) -> None:
        """Record a tyre-gauge reading per corner, consumed 0-1.

        A corner he did not read stays null.  Null here has to survive: a zero
        would read as a fresh tyre and would be believed, which is the failure
        mode CLAUDE.md calls absolute.

        `source` is `driver` for his own eyes on the gauge and `hud-video` for
        the same gauge read off an OBS capture.  **A driver reading is never
        overwritten by a video one**: CLAUDE.md §4.1 makes his report primary
        evidence and the video corroboration, so where the two disagree the
        disagreement has to stay visible rather than be resolved by whichever
        was written last.  A video reading may replace an earlier video
        reading, which is just a re-run of the same tool.
        """
        for name, value in (("fl", fl), ("fr", fr), ("rl", rl), ("rr", rr)):
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"wear is a fraction consumed, 0-1, got {value} for {name}")
        with self._write() as conn:
            if source != WEAR_DRIVER:
                row = conn.execute(
                    "SELECT wear_source, wear_fl, wear_fr, wear_rl, wear_rr "
                    "FROM laps WHERE id = ?", (lap_id,)).fetchone()
                held = row is not None and any(
                    row[i] is not None for i in range(1, 5))
                if held and (row[0] or WEAR_DRIVER) == WEAR_DRIVER:
                    return
            conn.execute(
                "UPDATE laps SET wear_fl = ?, wear_fr = ?, wear_rl = ?, "
                "wear_rr = ?, wear_source = ? WHERE id = ?",
                (fl, fr, rl, rr, source, lap_id))

    # --------------------------------------------------------- corner models

    def save_corner_model(self, circuit_key: str, model) -> None:
        with self._write() as conn:
            conn.execute(
                "INSERT INTO corner_models (circuit_key, model_id, version, source, "
                "lap_length_m, corners_json, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(circuit_key) DO UPDATE SET "
                "model_id=excluded.model_id, version=excluded.version, "
                "source=excluded.source, lap_length_m=excluded.lap_length_m, "
                "corners_json=excluded.corners_json, updated_at=excluded.updated_at",
                (circuit_key, model.model_id, model.version, model.source,
                 model.lap_length_m, json.dumps(model.as_dict()), _now(), _now()))

    # -------------------------------------------------------- track clock

    def save_track_clock(self, circuit_key: str, preset: str,
                         reading) -> None:
        """Record what this lobby preset does at this circuit.

        Only ever written from a measurement. A reading that measured nothing
        is not stored, because an empty row would read as "this preset holds a
        fixed time of day" - which is a real and different finding.
        """
        if not reading.measured:
            return
        with self._write() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO track_clock "
                "(circuit_key, preset, start_hour, multiplier, stops_at_hour, "
                " laps_sampled, updated_at) VALUES (?,?,?,?,?,?,?)",
                (circuit_key, preset or "", reading.start_hour,
                 reading.multiplier, reading.stopped_at_hour,
                 reading.laps_sampled, _now()))

    def get_track_clock(self, circuit_key: str, preset: str) -> dict | None:
        rows = self._query(
            "SELECT * FROM track_clock WHERE circuit_key = ? AND preset = ?",
            (circuit_key, preset or ""))
        return dict(rows[0]) if rows else None

    def list_track_clocks(self, circuit_key: str) -> list[dict]:
        """Every preset measured at this circuit, so the driver can see what
        the lobby's names actually mean here."""
        return [dict(row) for row in self._query(
            "SELECT * FROM track_clock WHERE circuit_key = ? ORDER BY "
            "start_hour", (circuit_key,))]

    def get_corner_model(self, circuit_key: str):
        from pitcrew.analysis.corner_model import CornerModel
        rows = self._query(
            "SELECT corners_json FROM corner_models WHERE circuit_key = ?",
            (circuit_key,))
        if not rows:
            return None
        return CornerModel.from_dict(json.loads(rows[0]["corners_json"]))

    def list_corner_models(self) -> list[str]:
        rows = self._query("SELECT circuit_key FROM corner_models ORDER BY circuit_key")
        return [r["circuit_key"] for r in rows]

    def frames_meta(self, lap_id: int) -> dict | None:
        """`sample_hz` and `frame_count` for a lap, without decoding it.

        **`get_lap_frames` costs 65-160 ms because it decompresses and JSON-
        parses a 481 KB blob; these two are plain columns beside it.** A
        caller that wanted only the rate was paying the whole decode for it -
        `analysis/grip.derive_event` did exactly that, once per lap, and it
        was 21.7 s of a 67.6 s call.

        Worse than slow: `json.loads` does not release the GIL, so every one
        of those decodes was tens of milliseconds during which the audio
        callback could not run. See `telemetry/recorder.ENCODE_CHUNK_ROWS`.
        """
        rows = self._query(
            "SELECT sample_hz, frame_count FROM lap_frames WHERE lap_id = ?",
            (lap_id,))
        if not rows:
            return None
        return {"sample_hz": rows[0]["sample_hz"],
                "frame_count": rows[0]["frame_count"]}

    def get_lap_frames(self, lap_id: int) -> dict | None:
        """Return {sample_hz, frame_count, frame_schema_version, frames} or None.

        `frame_schema_version` is the blob's own stamp, lifted out before
        `repair_frames` strips it. It is here because a v1 lap's yaw rate is
        reconstructed from the stored path and a v2 lap's comes off the packet,
        and the two differ by 3-4% at the top of the acceleration distribution -
        the same size as the compound step the tyre model exists to detect. A
        caller that cannot tell them apart will read a storage-format change as
        a physics finding, so the fact travels with the frames.
        """
        rows = self._query("SELECT * FROM lap_frames WHERE lap_id = ?", (lap_id,))
        if not rows:
            return None
        from pitcrew.telemetry.recorder import (
            FRAME_SCHEMA_VERSION,
            _VERSION_KEY,
            decode_frames,
            repair_frames,
        )
        row = rows[0]
        decoded = decode_frames(row["blob"])
        version = (decoded[0].get(_VERSION_KEY, FRAME_SCHEMA_VERSION)
                   if decoded else FRAME_SCHEMA_VERSION)
        return {
            "sample_hz": row["sample_hz"],
            "frame_count": row["frame_count"],
            "frame_schema_version": int(version),
            # Laps recorded before the lap-distance channel existed, and
            # before the clock was taken off GT7's time of day, are repaired
            # here - so a session captured last week still yields corners
            # rather than having to be run again.
            "frames": repair_frames(decoded, row["sample_hz"]),
        }

    def has_frames(self, lap_id: int) -> bool:
        return bool(self._query(
            "SELECT 1 FROM lap_frames WHERE lap_id = ?", (lap_id,)))

    # ---------------------------------------------------- the tyre model
    #
    # Two tables, both written only by the offline pipeline. Nothing on the
    # telemetry thread reaches either of them: the frames are already on disk
    # and re-aggregating them is what `CLAUDE.md` §6 kept them for.

    # Every column `write_grip_observations` will accept. A whitelist rather
    # than a free-form insert because the caller builds a dict per row, and a
    # misspelled key would otherwise be dropped in silence - which for a
    # covariate reads downstream as "not measured" and is indistinguishable
    # from the truth.
    GRIP_OBSERVATION_COLUMNS = (
        "lap_id", "unit_kind", "unit_id",
        "derivation_version", "frame_schema_version", "yaw_source",
        "corner_model_version", "sample_frames",
        "car_key", "circuit_key", "compound", "session_id", "lap_num",
        "stint_key", "lap_in_stint",
        "grip_g", "grip_stat", "lat_p95_g", "decel_p90_g", "min_speed_kph",
        "lap_time_ms",
        "temp_front_c", "temp_rear_c", "temp_front_max_c", "temp_rear_max_c",
        "entry_temp_front_c", "entry_temp_rear_c",
        "fuel_l", "laps_on_set", "gauge_worst_frac",
        "tod_ms", "clock_frozen", "session_elapsed_s",
        "commit_brake_pct", "commit_full_thr_frac", "kerb_frac",
        "apex_m_model", "apex_m_observed", "apex_anchor_laps",
        "apex_anchor_sd_m", "apex_instability", "identity_stable",
        "counts_toward_fit", "exclusion_reason",
    )

    def write_grip_observations(self, rows: list[dict]) -> int:
        """Store derived grip observations, replacing any of the same version.

        Idempotent by `(lap_id, unit_kind, unit_id, derivation_version)`: a
        second run at the same derivation version overwrites its own rows and
        leaves every other version alone. That is what makes a fitted model
        still resolvable - it names a derivation version, and the observations
        it was fitted on are still there under it.
        """
        if not rows:
            return 0
        unknown: set[str] = set()
        for row in rows:
            unknown |= set(row) - set(self.GRIP_OBSERVATION_COLUMNS)
        if unknown:
            raise ValueError(
                f"not a grip observation column: {', '.join(sorted(unknown))}")

        columns = [*self.GRIP_OBSERVATION_COLUMNS, "derived_at"]
        marks = ", ".join("?" for _ in columns)
        stamp = _now()
        with self._write() as conn:
            for row in rows:
                values = [row.get(name) for name in
                          self.GRIP_OBSERVATION_COLUMNS]
                conn.execute(
                    f"INSERT OR REPLACE INTO grip_observations "
                    f"({', '.join(columns)}) VALUES ({marks})",
                    [*values, stamp])
        return len(rows)

    def list_grip_observations(self, *, derivation_version: int | None = None,
                               unit_kind: str | None = None,
                               car_key: str | None = None,
                               circuit_key: str | None = None,
                               counted_only: bool = False) -> list[dict]:
        """Stored observations, narrowed by scope.

        Nothing here filters by `yaw_source` — that is the fitting layer's
        refusal to make, and hiding it behind a default here would turn a
        deliberate refusal into an invisible one.
        """
        where, params = [], []
        if derivation_version is not None:
            where.append("derivation_version = ?")
            params.append(derivation_version)
        if unit_kind is not None:
            where.append("unit_kind = ?")
            params.append(unit_kind)
        if car_key is not None:
            where.append("car_key = ?")
            params.append(car_key)
        if circuit_key is not None:
            where.append("circuit_key = ?")
            params.append(circuit_key)
        if counted_only:
            where.append("counts_toward_fit = 1")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        return [dict(r) for r in self._query(
            f"SELECT * FROM grip_observations {clause} "
            f"ORDER BY session_id, lap_num, unit_kind, unit_id", params)]

    def grip_derivation_versions(self) -> list[int]:
        return [int(r["derivation_version"]) for r in self._query(
            "SELECT DISTINCT derivation_version FROM grip_observations "
            "ORDER BY derivation_version")]

    def save_tyre_model(self, model: dict) -> int:
        """Write one fitted model, replacing the same scope at the same version.

        Deleted-then-inserted rather than upserted because `compound` is
        nullable and sqlite counts two NULLs as distinct in a UNIQUE index — so
        a compound-agnostic fit would accumulate a new row on every run and the
        newest would not be findable by the constraint.
        """
        # **`game_version` is part of the identity, not a column on it.** It
        # became a scope key when 1.71 was found pooling into pre-patch fits -
        # see `tyre_model.Scope` - and a key the storage does not know about is
        # not a key. Without it the v1.71 Monza fit DELETED the v1.70 one it
        # was meant to sit beside: 74 laps of pre-patch evidence vanished on
        # write, silently, and the archive kept only the 21 post-patch laps
        # under a row that still read like the whole record.
        keys = ("car_key", "circuit_key", "compound", "yaw_source",
                "model_kind", "derivation_version", "game_version")
        missing = [k for k in keys if k not in model]
        if missing:
            raise ValueError(f"a tyre model needs {', '.join(missing)}")
        payload = {
            **{k: model[k] for k in keys},
            "model_json": json.dumps(model.get("model", {})),
            "samples": int(model["samples"]),
            "sessions": int(model["sessions"]),
            "stints": int(model["stints"]),
            "confidence": model["confidence"],
            "speakable": int(bool(model.get("speakable"))),
            "gate_json": json.dumps(model.get("gate", {})),
            "unknowns_json": json.dumps(list(model.get("unknowns", ()))),
            "provenance_json": json.dumps(model.get("provenance", {})),
            "fitted_at": _now(),
        }
        with self._write() as conn:
            conn.execute(
                "DELETE FROM tyre_models WHERE car_key = ? AND circuit_key = ? "
                "AND compound IS ? AND yaw_source = ? AND model_kind = ? "
                "AND derivation_version = ? AND game_version IS ?",
                [model[k] for k in keys])
            cur = conn.execute(
                f"INSERT INTO tyre_models ({', '.join(payload)}) "
                f"VALUES ({', '.join('?' for _ in payload)})",
                list(payload.values()))
            return int(cur.lastrowid)

    def clear_tyre_models(self, derivation_version: int) -> int:
        """Drop every model fitted at one derivation version.

        A fit is regenerated wholesale from the observations at its version, so
        the previous run's rows are not history worth keeping - and if a scope
        key has changed between runs, they are worse than that. **A stale row
        under an old key does not collide with the new one and is not deleted
        by the upsert**, so it survives as a second answer to the same
        question. That is exactly what happened when one car was keyed two
        ways, so the regeneration is explicit rather than incremental.
        """
        with self._write() as conn:
            cur = conn.execute(
                "DELETE FROM tyre_models WHERE derivation_version = ?",
                (derivation_version,))
            return int(cur.rowcount or 0)

    def list_tyre_models(self, *, car_key: str | None = None,
                         circuit_key: str | None = None,
                         model_kind: str | None = None,
                         speakable_only: bool = False) -> list[dict]:
        where, params = [], []
        for column, value in (("car_key", car_key), ("circuit_key", circuit_key),
                              ("model_kind", model_kind)):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        if speakable_only:
            where.append("speakable = 1")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._query(
            f"SELECT * FROM tyre_models {clause} ORDER BY fitted_at DESC, id DESC",
            params)
        return [_tyre_model_row(r) for r in rows]

    # ------------------------------------------------------------ strategies

    def save_strategy(self, event_id: int, plan: dict, *, label: str | None = None,
                      evidence: dict | None = None, status: str = "candidate") -> int:
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO strategies (event_id, status, label, plan_json, "
                "evidence_json, created_at) VALUES (?,?,?,?,?,?)",
                (event_id, status, label, json.dumps(plan),
                 json.dumps(evidence) if evidence is not None else None, _now()))
            return int(cur.lastrowid)

    def approve_strategy(self, strategy_id: int) -> None:
        """Make this the approved plan, demoting whatever held that status."""
        with self._write() as conn:
            row = conn.execute("SELECT event_id FROM strategies WHERE id = ?",
                               (strategy_id,)).fetchone()
            if row is None:
                raise ValueError(f"no strategy with id {strategy_id}")
            conn.execute(
                "UPDATE strategies SET status = 'candidate' "
                "WHERE event_id = ? AND status = 'approved'", (row["event_id"],))
            conn.execute("UPDATE strategies SET status = 'approved' WHERE id = ?",
                         (strategy_id,))

    def get_approved_strategy(self, event_id: int) -> dict | None:
        rows = self._query(
            "SELECT * FROM strategies WHERE event_id = ? AND status = 'approved' "
            "ORDER BY created_at DESC LIMIT 1", (event_id,))
        return _strategy_row(rows[0]) if rows else None

    def list_strategies(self, event_id: int) -> list[dict]:
        rows = self._query(
            "SELECT * FROM strategies WHERE event_id = ? ORDER BY created_at DESC",
            (event_id,))
        return [_strategy_row(r) for r in rows]

    # ------------------------------------------------------------- race runs

    def start_race_run(self, event_id: int, strategy_id: int | None,
                       session_id: int | None) -> int:
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO race_runs (event_id, strategy_id, session_id, started_at) "
                "VALUES (?,?,?,?)", (event_id, strategy_id, session_id, _now()))
            return int(cur.lastrowid)

    def finish_race_run(self, race_run_id: int) -> None:
        with self._write() as conn:
            conn.execute("UPDATE race_runs SET finished_at = ? WHERE id = ?",
                         (_now(), race_run_id))

    def list_race_runs(self, event_id: int) -> list[dict]:
        rows = self._query(
            "SELECT * FROM race_runs WHERE event_id = ? ORDER BY id",
            (event_id,))
        return [dict(r) for r in rows]

    def record_traffic(self, session_id: int, rows: list[dict]) -> int:
        """File one session's radar contacts, replacing whatever was there.

        Replaced rather than appended because a re-read of the same capture at
        a finer interval is a better answer to the same question, not a second
        set of cars. `source` says which instrument produced them so a future
        one - a live feed that finally carries opponents - does not silently
        merge with this.
        """
        stamp = datetime.datetime.now().replace(microsecond=0).isoformat()
        with self._write() as conn:
            conn.execute("DELETE FROM traffic WHERE session_id = ?",
                         (session_id,))
            conn.executemany(
                "INSERT INTO traffic (session_id, lap_id, lap_num, video_s, "
                "side, ribbon_px, near_m, rival_position, source, read_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(session_id, r.get("lap_id"), r["lap_num"], r["video_s"],
                  r.get("side"), r.get("ribbon_px"), r.get("near_m"),
                  r.get("rival_position"), r.get("source", "replay-radar"),
                  stamp) for r in rows])
        return len(rows)

    def name_traffic(self, traffic_id: int, rival: str) -> None:
        """Put a name to one contact. Only ever from a labelled cluster."""
        with self._write() as conn:
            conn.execute("UPDATE traffic SET rival = ? WHERE id = ?",
                         (rival, traffic_id))

    def list_traffic(self, session_id: int) -> list[dict]:
        return [dict(r) for r in self._query(
            "SELECT * FROM traffic WHERE session_id = ? "
            "ORDER BY video_s", (session_id,))]

    def append_revision(self, race_run_id: int, lap_num: int, reason: str,
                        plan: dict, *, accepted: bool = False) -> int:
        """Append to the immutable revision chain for a race run."""
        with self._write() as conn:
            parent = conn.execute(
                "SELECT id FROM race_revisions WHERE race_run_id = ? "
                "ORDER BY id DESC LIMIT 1", (race_run_id,)).fetchone()
            cur = conn.execute(
                "INSERT INTO race_revisions (race_run_id, parent_id, lap_num, reason, "
                "accepted, plan_json, created_at) VALUES (?,?,?,?,?,?,?)",
                (race_run_id, parent["id"] if parent else None, lap_num, reason,
                 int(accepted), json.dumps(plan), _now()))
            return int(cur.lastrowid)

    def list_revisions(self, race_run_id: int) -> list[dict]:
        rows = self._query(
            "SELECT * FROM race_revisions WHERE race_run_id = ? ORDER BY id",
            (race_run_id,))
        out = []
        for row in rows:
            item = dict(row)
            item["plan"] = json.loads(item.pop("plan_json"))
            item["accepted"] = bool(item["accepted"])
            out.append(item)
        return out


def _event_row(row: sqlite3.Row) -> dict:
    event = dict(row)
    for key in ("available_compounds", "required_compounds"):
        raw = event.get(key) or "[]"
        event[key] = json.loads(raw)
    return event


def _setup_sheet(row: sqlite3.Row):
    from pitcrew.setup.sheet import SetupSheet
    return SetupSheet(
        car_name=row["car_name"],
        sheet_name=row["sheet_name"],
        values=json.loads(row["values_json"] or "{}"),
        gears=json.loads(row["gears_json"] or "[]"),
        shift_rpm={int(g): float(r) for g, r in json.loads(
            (row["shift_rpm_json"] if "shift_rpm_json" in row.keys() else None)
            or "{}").items()},
        performance=json.loads(row["performance_json"] or "{}"),
        build=json.loads(row["build_json"] or "{}"),
        notes=row["notes"] or "",
        purpose=row["purpose"] if "purpose" in row.keys() else None,
        circuit_key=(row["circuit_key"]
                     if "circuit_key" in row.keys() else None),
        id=row["id"],
    )


def _tyre_model_row(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["model"] = json.loads(item.pop("model_json"))
    item["gate"] = json.loads(item.pop("gate_json"))
    item["unknowns"] = json.loads(item.pop("unknowns_json"))
    item["provenance"] = json.loads(item.pop("provenance_json"))
    item["speakable"] = bool(item["speakable"])
    return item


def _strategy_row(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["plan"] = json.loads(item.pop("plan_json"))
    evidence = item.pop("evidence_json", None)
    item["evidence"] = json.loads(evidence) if evidence else None
    return item
