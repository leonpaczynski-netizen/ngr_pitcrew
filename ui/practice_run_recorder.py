"""PracticeRunRecorder — the write side of the guided practice loop (UAT-2 remediation).

``SessionDB.upsert_preparation_activity`` and ``bind_session_to_activity`` existed and
were tested, but no surface in the product ever called them. The consequence the driver
saw: nine laps of practice, and the Pit Crew Engineer still saying "setup_base is the
weakest domain (confidence: none)" — because the event programme had no activities, so
no sessions were bound, so cumulative evidence stayed empty forever.

This class closes that loop. It performs ONLY the two canonical writes, and only from
an explicit user action; every decision about *whether* to write is made by the pure
``strategy.practice_run_recording``. Qt-free and defensive — a failure here reports a
reason, it never raises into the UI.
"""

from __future__ import annotations

import datetime
from typing import Mapping, Optional

from strategy.practice_run_recording import (
    OPEN_STATES, PlannedRun, RunBindingDecision, completed_activity_row,
    discarded_activity_row, evaluate_run_binding, plan_practice_run,
)


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


class PracticeRunRecorder:
    """Starts, records and discards practice runs against the active preparation cycle."""

    def __init__(self, db=None, config: Optional[dict] = None):
        self._db = db
        self._config = config if isinstance(config, dict) else {}

    # ---- reads ------------------------------------------------------------
    def active_cycle_id(self) -> str:
        """The explicitly-selected active cycle. Never guesses one."""
        try:
            return _norm(self._config.get("active_cycle_id"))
        except Exception:
            return ""

    def _activities(self, cycle_id: str) -> list:
        try:
            if self._db is None or not hasattr(self._db, "list_preparation_activities"):
                return []
            return list(self._db.list_preparation_activities(cycle_id) or [])
        except Exception:
            return []

    def open_run(self) -> Optional[dict]:
        """The activity currently in progress for the active cycle, or None."""
        cid = self.active_cycle_id()
        if not cid:
            return None
        for a in self._activities(cid):
            if isinstance(a, Mapping) and _norm(a.get("state")).lower() in OPEN_STATES:
                row = dict(a)
                row.setdefault("cycle_id", cid)
                return row
        return None

    def _cycle(self, cycle_id: str) -> dict:
        try:
            if self._db is None or not hasattr(self._db, "get_preparation_cycle"):
                return {}
            return dict(self._db.get_preparation_cycle(cycle_id) or {})
        except Exception:
            return {}

    # ---- writes -----------------------------------------------------------
    def start_run(self, *, objective_domain: str = "",
                  objective_headline: str = "") -> PlannedRun:
        """Open a preparation activity for the run the driver is about to do.

        This is the explicit user action that gives the run a purpose — which is what
        decides the evidence domains it can contribute to when it is later bound.
        """
        cid = self.active_cycle_id()
        plan = plan_practice_run(
            cycle_id=cid, objective_domain=objective_domain,
            objective_headline=objective_headline,
            existing_activities=self._activities(cid))
        if not plan.ok or plan.reused:
            return plan
        if self._db is None or not hasattr(self._db, "upsert_preparation_activity"):
            return PlannedRun(reason="No event database available to record the run.")
        try:
            now = _now_iso()
            self._db.upsert_preparation_activity(plan.as_activity_row(now_iso=now, created_at=now))
        except Exception as exc:  # pragma: no cover - defensive
            return PlannedRun(reason=f"Could not open the run: {exc}")
        return plan

    def record_run(self, session_id, session_meta: Optional[Mapping] = None) -> RunBindingDecision:
        """Bind the completed telemetry session to the open run and close it.

        This is the ONLY path by which a session becomes event evidence — sessions are
        never auto-bound. On success the preparation report gains the session, cumulative
        evidence moves, and the engineer's objective changes on the next refresh.
        """
        run = self.open_run()
        if run is None:
            return RunBindingDecision(reason="No run is open — press Start practice run first.")
        cid = _norm(run.get("cycle_id")) or self.active_cycle_id()
        meta = session_meta
        if meta is None:
            meta = self._session_meta(session_id)
        decision = evaluate_run_binding(
            activity_id=_norm(run.get("activity_id")), cycle_id=cid,
            session_id=session_id, session_meta=meta, cycle=self._cycle(cid))
        if not decision.ok:
            return decision
        if self._db is None or not hasattr(self._db, "bind_session_to_activity"):
            return RunBindingDecision(reason="No event database available to record the run.")
        try:
            now = _now_iso()
            self._db.bind_session_to_activity(
                decision.activity_id, decision.session_id, cycle_id=cid, created_at=now)
            self._db.upsert_preparation_activity(completed_activity_row(run, now_iso=now))
        except Exception as exc:  # pragma: no cover - defensive
            return RunBindingDecision(reason=f"Could not record the run: {exc}")
        return decision

    def discard_run(self) -> bool:
        """Abandon the open run without binding anything to it."""
        run = self.open_run()
        if run is None or self._db is None:
            return False
        try:
            self._db.upsert_preparation_activity(discarded_activity_row(run, now_iso=_now_iso()))
            return True
        except Exception:  # pragma: no cover - defensive
            return False

    # ---- helpers ----------------------------------------------------------
    def _session_meta(self, session_id) -> dict:
        try:
            if self._db is None or not hasattr(self._db, "get_session_meta"):
                return {}
            return dict(self._db.get_session_meta(int(session_id or 0)) or {})
        except Exception:
            return {}
