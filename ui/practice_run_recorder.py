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
import threading
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
        # Live references to off-thread proposal-generation threads so they
        # are not garbage-collected before they finish. Pruned after each call.
        self._proposal_threads: list = []
        # Sessions recorded where evidence exists but no owner baseline was
        # entered. Callers can surface these via no_baseline_sessions().
        self._no_baseline_sessions: list = []

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

    def recorded_runs(self) -> list:
        """Every run already bound to the active cycle, oldest first.

        The Practice Outcome compares this run against the one before it. That pair used
        to be held in two process-lifetime integers, so after every restart the newest
        run reported itself as "the first recorded run for this setup" and no comparison
        was ever possible across sessions. The programme already knows which runs are
        bound to the event — read them from there instead.

        Rows are ``{session_id: int, activity_id, activity_type, total_laps}``. Sorted
        NUMERICALLY: the binding table stores session ids as text, so its own ORDER BY
        puts session 10 before session 9.
        """
        cid = self.active_cycle_id()
        if not cid or self._db is None or not hasattr(self._db, "get_practice_sessions_for_cycle"):
            return []
        try:
            rows = list(self._db.get_practice_sessions_for_cycle(cid) or [])
        except Exception:
            return []
        out = []
        for r in rows:
            if not isinstance(r, Mapping):
                continue
            try:
                sid = int(str(r.get("session_id") or "0").strip() or 0)
            except (TypeError, ValueError):
                continue
            if sid <= 0:
                continue
            out.append({"session_id": sid,
                        "activity_id": _norm(r.get("activity_id")),
                        "activity_type": _norm(r.get("activity_type")),
                        "total_laps": int(r.get("total_laps") or 0)})
        out.sort(key=lambda x: x["session_id"])
        return out

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
        # After a successful bind, trigger owner-baseline proposal generation off
        # the Qt thread. This never blocks record_run — proposal generation is
        # best-effort and non-fatal (never raises into the UI). The brief requires
        # this to happen after record_run, off the Qt thread (B part, practice path).
        self._trigger_owner_proposals(session_id, meta)
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

    def no_baseline_sessions(self) -> list:
        """Sessions where evidence was collected but no owner baseline was entered.

        Returns a list of dicts ``{session_id, event_id, discipline, note}``.
        The UI should surface these as "evidence collected, no baseline" (not as
        failures) and NEVER offer to auto-generate a baseline from them (decision R2).
        """
        return list(self._no_baseline_sessions)

    def _trigger_owner_proposals(self, session_id, session_meta=None) -> None:
        """Trigger owner-baseline proposal generation off the Qt thread (B part).

        ONLY runs when an owner baseline has been entered for the discipline.
        When no baseline exists the session is flagged "evidence collected, no
        baseline" — decision R2 prevents auto-generating a baseline.

        Uses a daemon threading.Thread so shutdown never blocks on this work.
        Never raises — proposal generation failure is non-fatal.
        """
        try:
            if self._db is None:
                return
            # Resolve the session_run (uuid) from the integer session_id.
            session_run = None
            if hasattr(self._db, "get_run_for_session"):
                session_run = self._db.get_run_for_session(int(session_id or 0))
            if not session_run:
                return  # no session_run row yet — nothing to propose against
            event_id = int(session_run.get("event_id") or 0)
            run_id = str(session_run.get("run_id") or "")
            if not event_id or not run_id:
                return

            # Determine discipline from session_type (Practice → race baseline;
            # Qualifying → qualifying baseline).
            meta = session_meta or self._session_meta(session_id)
            session_type_str = str(meta.get("session_type") or "").lower()
            discipline = "qualifying" if "qual" in session_type_str else "race"

            # Check whether an owner baseline exists for this event + discipline.
            baseline = None
            if hasattr(self._db, "get_owner_baseline"):
                baseline = self._db.get_owner_baseline(event_id, discipline)

            if baseline is None:
                # Evidence collected, but owner has not entered a baseline.
                # Surface this state to the UI; do NOT auto-generate (R2).
                # M3: also persist the flag to the DB so it survives restarts.
                self._no_baseline_sessions.append({
                    "session_id": int(session_id or 0),
                    "event_id": event_id,
                    "discipline": discipline,
                    "note": "evidence collected, no baseline",
                })
                if run_id and hasattr(self._db, "mark_evidence_without_baseline"):
                    try:
                        self._db.mark_evidence_without_baseline(
                            event_id, discipline, run_id)
                    except Exception:
                        pass  # non-fatal; in-memory flag was already recorded
                return

            # Spawn off-thread proposal generation. The thread is a daemon so it
            # never blocks application shutdown.
            db = self._db

            def _run() -> None:
                try:
                    from services import owner_baseline_service
                    owner_baseline_service.run_for_session(
                        db,
                        session_run_id=run_id,
                        discipline=discipline,
                    )
                except Exception:
                    pass  # non-fatal — never propagate

            t = threading.Thread(
                target=_run,
                daemon=True,
                name=f"owner_proposal_{run_id[:8]}",
            )
            t.start()
            self._proposal_threads.append(t)
            # Prune finished threads so the list stays small.
            self._proposal_threads = [
                t for t in self._proposal_threads if t.is_alive()
            ]
        except Exception:
            pass  # never propagate — record_run must always succeed if possible

    # ---- helpers ----------------------------------------------------------
    def _session_meta(self, session_id) -> dict:
        try:
            if self._db is None or not hasattr(self._db, "get_session_meta"):
                return {}
            return dict(self._db.get_session_meta(int(session_id or 0)) or {})
        except Exception:
            return {}
