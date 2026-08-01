"""SessionDB adapter for the live Practice recording coordinator (Program 3, Live Activation 1).

The production ``LivePracticePort``: it turns the coordinator's decisions into real writes on
``SessionDB`` and hands back the resolved canonical context. Qt-free (like
``practice_run_recorder``); the DB is the only I/O. A resolver callable supplies the context so
the same adapter is exercised by the shell bridge and by offline tests against a real in-memory
``SessionDB``.

It reuses the spine that already exists — ``open_session`` creates the canonical
``session_run`` (+ opening stint) and ``write_lap`` stamps every lap with its
``session_run_id``/``stint_id`` — so this adapter only *authorises* the run (binds it to the
planned session) and drives status; the raw persistence stays where it is proven.
"""
from __future__ import annotations

import datetime
from typing import Callable, Mapping, Optional, Tuple


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class SessionDbLivePracticePort:
    """Adapts SessionDB to the LivePracticePort protocol."""

    def __init__(self, db, context_resolver: Callable[[], Mapping]):
        self._db = db
        self._resolve = context_resolver
        self._session_id: int = 0
        self._run_id: str = ""

    # -- port surface ------------------------------------------------------ #
    def resolve_activation_context(self) -> Mapping:
        try:
            ctx = self._resolve() or {}
        except Exception:
            ctx = {}
        return ctx if isinstance(ctx, Mapping) else {}

    def create_run(self, identity: Mapping) -> Tuple[str, str]:
        """Open the recording session (spine auto-creates the canonical run + stint), bind it
        to the planned session, and return (run_id, stint_id). Returns ('','') on failure —
        the coordinator treats an empty run as unrecordable."""
        idn = dict(identity if isinstance(identity, Mapping) else {})
        # The gate's identity carries only canonical fields; pull the live session + open-session
        # params from the full resolved context.
        try:
            full = self._resolve() or {}
            for k in ("live_session_id", "track", "car_name", "config_id", "layout_id",
                      "driver_id", "gt7_version"):
                if not _norm(idn.get(k)) and k in full:
                    idn[k] = full[k]
        except Exception:
            pass
        # LIVE: adopt the telemetry session the dispatcher already opened (never open a second
        # session for the same recording). OFFLINE/tests: open one. The spine's open_session /
        # _attach_session_run already created the canonical run + stint either way.
        adopt = _int(idn.get("live_session_id"))
        try:
            if adopt > 0:
                self._session_id = adopt
            else:
                self._session_id = int(self._db.open_session(
                    _int(idn.get("car_id")), _norm(idn.get("track")),
                    (_norm(idn.get("session_type")).title() or "Practice"),
                    car_name=_norm(idn.get("car_name")), config_id=_norm(idn.get("config_id")),
                    event_id=_int(idn.get("event_id")),
                    layout_id=_norm(idn.get("layout_id")),
                    driver_id=_norm(idn.get("driver_id")),
                    gt7_version=_norm(idn.get("gt7_version"))))
        except Exception:
            return "", ""
        run = None
        try:
            run = self._db.get_run_for_session(self._session_id)
        except Exception:
            run = None
        if not run:
            return "", ""
        self._run_id = _norm(run.get("run_id"))
        # Bind the authoritative run to its planned session (the spine leaves it unbound).
        plan = _norm(idn.get("session_plan_id"))
        if plan:
            try:
                self._db.bind_run_to_plan(self._run_id, plan)
            except Exception:
                pass
        stint_id = ""
        try:
            stint_id = _norm(self._db.first_stint_id(self._run_id))
        except Exception:
            stint_id = ""
        return self._run_id, stint_id

    def persist_lap(self, *, run_id: str, stint_id: str, lap_number: int, lap_time_ms: int,
                    valid: bool, invalid_reasons: Tuple[str, ...]) -> None:
        """Persist one accepted lap on the recording session; ``write_lap`` stamps it with
        the run + stint automatically. Best-effort — never raises into the caller."""
        reasons = set(invalid_reasons or ())
        try:
            self._db.write_lap(
                self._session_id, int(lap_number), int(lap_time_ms), 0.0, None,
                event_id=_int((self._resolve() or {}).get("event_id")),
                session_type="Practice",
                is_out_lap=("out_lap" in reasons), is_pit_lap=("pit_lap" in reasons))
        except Exception:
            pass

    def set_run_status(self, run_id: str, status: str) -> None:
        try:
            ended = datetime.datetime.now(datetime.timezone.utc).isoformat() \
                if status in ("completed", "abandoned") else ""
            self._db.set_session_run_status(_norm(run_id), _norm(status), ended)
        except Exception:
            pass

    # -- read helpers (for the UI / verification) -------------------------- #
    @property
    def session_id(self) -> int:
        return self._session_id
