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
        """
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
            return int(cur.lastrowid)

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

    # ----------------------------------------------------- setup (app state)

    def save_setup_sheet(self, sheet) -> int:
        """Insert or update a sheet by (car, name).  Returns its id."""
        sheet.validate()
        with self._write() as conn:
            conn.execute(
                "INSERT INTO setup_sheets (car_name, sheet_name, values_json, "
                "gears_json, performance_json, build_json, notes, purpose, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(car_name, sheet_name) DO UPDATE SET "
                "values_json=excluded.values_json, gears_json=excluded.gears_json, "
                "performance_json=excluded.performance_json, "
                "build_json=excluded.build_json, notes=excluded.notes, "
                "purpose=excluded.purpose, "
                "updated_at=excluded.updated_at",
                (sheet.car_name, sheet.sheet_name, json.dumps(sheet.values),
                 json.dumps(sheet.gears), json.dumps(sheet.performance),
                 json.dumps(sheet.build), sheet.notes, sheet.purpose,
                 _now(), _now()))
            row = conn.execute(
                "SELECT id FROM setup_sheets WHERE car_name = ? AND sheet_name = ?",
                (sheet.car_name, sheet.sheet_name)).fetchone()
            return int(row["id"])

    def get_setup_sheet(self, sheet_id: int):
        rows = self._query("SELECT * FROM setup_sheets WHERE id = ?", (sheet_id,))
        return _setup_sheet(rows[0]) if rows else None

    def sheet_for(self, car_name: str, purpose: str):
        """The car's most recent sheet for this purpose, or None.

        A sheet with no purpose on it is a candidate for `race` only. It
        predates the question, and every sheet stored before it was asked
        was a race sheet - a qualifying sheet that was never labelled as
        one has to be labelled rather than assumed.
        """
        wanted = [sheet for sheet in self.list_setup_sheets(car_name)
                  if sheet.purpose == purpose
                  or (purpose == "race" and sheet.purpose is None)]
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

    def add_setup_change(self, session_id: int, change) -> int:
        change.validate()
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO setup_changes (session_id, from_lap, key, from_value, "
                "to_value, created_at) VALUES (?,?,?,?,?,?)",
                (session_id, change.from_lap, change.key, change.from_value,
                 change.to_value, _now()))
            return int(cur.lastrowid)

    def list_setup_changes(self, session_id: int) -> list:
        from pitcrew.setup.sheet import SetupChange
        rows = self._query(
            "SELECT * FROM setup_changes WHERE session_id = ? ORDER BY from_lap, id",
            (session_id,))
        return [SetupChange(from_lap=r["from_lap"], key=r["key"],
                            from_value=r["from_value"], to_value=r["to_value"])
                for r in rows]

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
                      rehearsal: bool = False) -> int:
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (event_id, kind, tune_label, setup_sheet_id, "
                "practice_mode, practice_intent, rehearsal, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, kind, tune_label, setup_sheet_id, practice_mode,
                 practice_intent, int(rehearsal), _now()))
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
                          fuel_capacity_l: float | None = None) -> None:
        """Record what the stream actually delivered, once it is known."""
        with self._write() as conn:
            conn.execute(
                "UPDATE sessions SET packet_format = COALESCE(?, packet_format), "
                "car_category = COALESCE(?, car_category), "
                "fuel_capacity_l = COALESCE(?, fuel_capacity_l) WHERE id = ?",
                (packet_format, car_category, fuel_capacity_l, session_id))

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
            cur = conn.execute(
                "INSERT OR REPLACE INTO laps "
                "(session_id, lap_num, lap_time_ms, delta_ms, fuel_start, fuel_end, "
                " fuel_used, position, compound, is_pit_lap, is_out_lap, gear_ratios, "
                " tyres_changed, fuel_added_l, tod_start_ms, tod_end_ms, "
                " standing_start_ms, crawl_s, off_track_s, spin_s, "
                " recorded_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                 _now()))
            lap_id = int(cur.lastrowid)
            if frames is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO lap_frames "
                    "(lap_id, sample_hz, frame_count, blob) VALUES (?,?,?,?)",
                    (lap_id, frames.sample_hz, frames.frame_count, frames.blob))
            return lap_id

    def list_laps(self, session_id: int) -> list[dict]:
        rows = self._query(
            "SELECT * FROM laps WHERE session_id = ? ORDER BY lap_num", (session_id,))
        return [dict(r) for r in rows]

    def list_evidence_laps(self, event_id: int) -> list[dict]:
        """Every lap that says something about how this event will go.

        Practice, **and any race run as a rehearsal**. Not the league race
        itself: that is the thing being planned for, and a plan built on the
        race it is planning is not a plan.

        A rehearsal is the better evidence of the two and it is the only place
        some of it comes from at all. It is run at race fuel load, at race
        pace, in traffic, at the race's time of day, and it makes a real pit
        stop - so the refuel rate, the pit loss and whether a stint length
        survives a cold out-lap are all measured there rather than assumed.
        Recording one and then not reading it, which is what the app did until
        now, is the whole feature missing its point.
        """
        rows = self._query(
            "SELECT laps.*, sessions.started_at AS session_started, "
            "       sessions.practice_mode AS practice_mode, "
            "       sessions.practice_intent AS practice_intent, "
            "       sessions.setup_sheet_id AS setup_sheet_id, "
            "       sessions.kind AS session_kind, "
            "       COALESCE(sessions.rehearsal, 0) AS rehearsal "
            "FROM laps JOIN sessions ON sessions.id = laps.session_id "
            "WHERE sessions.event_id = ? "
            "  AND (sessions.kind = 'practice' OR sessions.rehearsal = 1) "
            "ORDER BY sessions.started_at, sessions.id, laps.lap_num",
            (event_id,))
        return [dict(r) for r in rows]

    def list_event_laps(self, event_id: int, kind: str = "practice") -> list[dict]:
        rows = self._query(
            "SELECT laps.*, sessions.started_at AS session_started, "
            "       sessions.practice_mode AS practice_mode, "
            "       sessions.practice_intent AS practice_intent, "
            "       sessions.setup_sheet_id AS setup_sheet_id, "
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
                     rl: float | None, rr: float | None) -> None:
        """Record the driver's tyre-gauge reading per corner, consumed 0-1.

        A corner he did not read stays null.  Null here has to survive: a zero
        would read as a fresh tyre and would be believed, which is the failure
        mode CLAUDE.md calls absolute.
        """
        for name, value in (("fl", fl), ("fr", fr), ("rl", rl), ("rr", rr)):
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"wear is a fraction consumed, 0-1, got {value} for {name}")
        with self._write() as conn:
            conn.execute(
                "UPDATE laps SET wear_fl = ?, wear_fr = ?, wear_rl = ?, "
                "wear_rr = ? WHERE id = ?", (fl, fr, rl, rr, lap_id))

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

    def get_lap_frames(self, lap_id: int) -> dict | None:
        """Return {sample_hz, frame_count, frames: [dict, ...]} or None."""
        rows = self._query("SELECT * FROM lap_frames WHERE lap_id = ?", (lap_id,))
        if not rows:
            return None
        from pitcrew.telemetry.recorder import decode_frames, repair_frames
        row = rows[0]
        return {
            "sample_hz": row["sample_hz"],
            "frame_count": row["frame_count"],
            # Laps recorded before the lap-distance channel existed, and
            # before the clock was taken off GT7's time of day, are repaired
            # here - so a session captured last week still yields corners
            # rather than having to be run again.
            "frames": repair_frames(decode_frames(row["blob"]),
                                    row["sample_hz"]),
        }

    def has_frames(self, lap_id: int) -> bool:
        return bool(self._query(
            "SELECT 1 FROM lap_frames WHERE lap_id = ?", (lap_id,)))

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
        performance=json.loads(row["performance_json"] or "{}"),
        build=json.loads(row["build_json"] or "{}"),
        notes=row["notes"] or "",
        purpose=row["purpose"] if "purpose" in row.keys() else None,
        id=row["id"],
    )


def _strategy_row(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["plan"] = json.loads(item.pop("plan_json"))
    evidence = item.pop("evidence_json", None)
    item["evidence"] = json.loads(evidence) if evidence else None
    return item
