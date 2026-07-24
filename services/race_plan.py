"""Building the race plan, headless (single-system slice 1).

The Race Strategy surface could only ever *display* a plan — it read
``window._last_race_plan_result``, which only the classic Race Plan tab could set. So a
driver working entirely in the new shell had a strategy page that stayed empty forever
with no way to fill it.

The pipeline itself was never the problem: ``recommend_strategy_from_session`` is pure
and evidence-based. Only its INPUTS were trapped, in three spin boxes and a session
dropdown on the classic tab. Everything else already came from ``EventContext``.

Two choices this makes that the classic tab left to the driver:

  * **Which session to plan from.** The classic tab offers a dropdown of recent
    sessions. In the guided flow the answer is known — the runs actually RECORDED
    against this event's preparation cycle, most recent first. A plan built from a run
    that was never recorded is a plan built from evidence the programme does not have.
  * **Pit loss.** The manual override is a classic-tab spin box. Without it the value
    comes from the frozen strategy snapshot — exactly the fallback the classic tab uses
    when that field is left at zero. Note the snapshot supplies its own default when
    nothing has been measured, so this is never "unknown"; that is the domain's
    long-standing behaviour, not a decision made here.

No Qt, no widgets. Synchronous: the caller decides where it runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _f(v, default=0.0) -> float:
    try:
        return float(v) if v not in (None, "") else float(default)
    except (TypeError, ValueError):
        return float(default)


def _i(v, default=0) -> int:
    try:
        return int(v) if v not in (None, "") else int(default)
    except (TypeError, ValueError):
        return int(default)


@dataclass(frozen=True)
class RacePlanResult:
    """The outcome of building a plan. ``ok`` False always carries a reason."""
    ok: bool = False
    reason: str = ""
    result: Any = None            # the raw pipeline result (for the live replan compare)
    view_model: Any = None        # build_race_plan_view_model(result)
    session_id: int = 0
    inputs: Dict[str, Any] = field(default_factory=dict)

    @property
    def headline(self) -> str:
        if not self.ok:
            return self.reason or "The race plan could not be built."
        return f"Race plan built from session {self.session_id}." if self.session_id \
            else "Race plan built."


class RacePlanService:
    """Builds an evidence-based race plan without a window."""

    def __init__(self, db=None, config: Optional[dict] = None):
        self._db = db
        self._config = config if isinstance(config, dict) else {}
        self._last: Optional[RacePlanResult] = None

    # ---- read -------------------------------------------------------------
    @property
    def last_plan(self) -> Optional[RacePlanResult]:
        return self._last

    def recorded_sessions(self) -> Tuple[int, ...]:
        """Session ids RECORDED against the active event, most recent first.

        These are the only sessions the programme counts as evidence — a plan built
        from anything else is built on data the event does not know about.
        """
        try:
            cycle = _norm(self._config.get("active_cycle_id"))
            if not cycle or self._db is None:
                return ()
            if not hasattr(self._db, "get_practice_sessions_for_cycle"):
                return ()
            rows = self._db.get_practice_sessions_for_cycle(cycle) or []
            ids = []
            for row in rows:
                sid = _i((row or {}).get("session_id"))
                if sid > 0 and int((row or {}).get("total_laps") or 0) > 0:
                    ids.append(sid)
            return tuple(sorted(set(ids), reverse=True))
        except Exception:
            return ()

    # ---- inputs -----------------------------------------------------------
    def _event_context(self):
        try:
            from services.setup_inputs import _event_context
            return _event_context(self._db, self._config)
        except Exception:
            return None

    def _car_id(self, car_name: str) -> int:
        try:
            if self._db is not None and car_name and hasattr(self._db, "get_car_id"):
                return _i(self._db.get_car_id(car_name))
        except Exception:
            pass
        return 0

    def _pit_loss_seconds(self) -> float:
        """Pit loss from the frozen strategy snapshot.

        The same fallback the classic tab uses when its manual field is left at zero.
        The snapshot supplies its own default when nothing has been measured, so this
        can return a value the driver never entered — that is existing domain behaviour
        and is surfaced by the plan's own measured-vs-assumed reporting.
        """
        try:
            from data.analysis_inputs import build_strategy_inputs
            snap = build_strategy_inputs(
                legacy_strategy=self._config.get("strategy") or {})
            return _f(snap.race_params_dict().get("pit_loss_secs"), 0.0)
        except Exception:
            return 0.0

    def build_inputs(self, session_id: int = 0) -> Dict[str, Any]:
        """Every input the strategy pipeline needs. Never raises."""
        ec = self._event_context()
        car = _norm(getattr(ec, "car", "")) or _norm(
            (self._config.get("strategy") or {}).get("car"))
        race_type = _norm(getattr(ec, "race_type", "lap")) or "lap"
        timed = race_type == "timed"
        return {
            "event_context": ec,
            "session_id": _i(session_id),
            "car_id": self._car_id(car),
            "car_name": car,
            "track": _norm(getattr(ec, "track", "")),
            "layout_id": _norm(getattr(ec, "layout_id", "")),
            "race_type": race_type,
            "race_laps": 0 if timed else _i(getattr(ec, "laps", 0)),
            "race_duration_minutes": _f(getattr(ec, "race_duration_minutes", 0)) if timed else 0.0,
            "fuel_multiplier": _f(getattr(ec, "fuel_multiplier", 0.0)),
            "tyre_multiplier": _f(getattr(ec, "tyre_wear_multiplier", 0.0)),
            "refuel_rate_lps": _f(getattr(ec, "refuel_rate_lps", 0.0)),
            "pit_loss_seconds": self._pit_loss_seconds(),
            "starting_fuel_pct": 100.0,     # GT7's tank is always 100% = 100 L
            "available_compounds": tuple(getattr(ec, "available_tyres", ()) or ()),
            "required_compounds": tuple(getattr(ec, "required_tyres", ()) or ()),
            "mandatory_pit_stops": _i(getattr(ec, "mandatory_stops", 0)),
        }

    # ---- build ------------------------------------------------------------
    def build_plan(self, session_id: int = 0) -> RacePlanResult:
        """Build the plan from a recorded run. Never raises."""
        sid = _i(session_id)
        if not sid:
            recorded = self.recorded_sessions()
            if not recorded:
                return RacePlanResult(reason=(
                    "No recorded run to plan from yet. Drive a practice run and press "
                    "“End run & record” — the plan is built from that evidence."))
            sid = recorded[0]

        inputs = self.build_inputs(sid)
        if not inputs["track"] or not inputs["car_name"]:
            return RacePlanResult(reason="Pick the car and track first.",
                                  session_id=sid, inputs=inputs)
        if not inputs["race_laps"] and not inputs["race_duration_minutes"]:
            return RacePlanResult(
                reason="This event has no race length set — add laps or a duration.",
                session_id=sid, inputs=inputs)

        rear_fragile = False
        try:
            from strategy.setup_driver_profile import build_driver_profile
            profile = build_driver_profile()
            rear_fragile = bool(profile.prefers_rear_stability or profile.dislikes_snap_exit)
        except Exception:
            rear_fragile = False

        try:
            from strategy.race_strategy_pipeline import recommend_strategy_from_session
            result = recommend_strategy_from_session(
                self._db,
                session_id=inputs["session_id"], car_id=inputs["car_id"],
                track=inputs["track"], layout_id=inputs["layout_id"],
                race_duration_minutes=inputs["race_duration_minutes"],
                race_laps=inputs["race_laps"],
                fuel_multiplier=inputs["fuel_multiplier"],
                tyre_multiplier=inputs["tyre_multiplier"],
                refuel_rate_lps=inputs["refuel_rate_lps"],
                pit_loss_seconds=inputs["pit_loss_seconds"],
                starting_fuel_pct=inputs["starting_fuel_pct"],
                available_compounds=inputs["available_compounds"],
                required_compounds=inputs["required_compounds"],
                mandatory_pit_stops=inputs["mandatory_pit_stops"],
                rear_traction_fragile=rear_fragile)
        except Exception as exc:
            return RacePlanResult(reason=f"The race plan could not be built: {exc}",
                                  session_id=sid, inputs=inputs)

        try:
            from ui.race_strategy_vm import build_race_plan_view_model
            view_model = build_race_plan_view_model(result)
        except Exception as exc:
            return RacePlanResult(reason=f"The plan could not be rendered: {exc}",
                                  result=result, session_id=sid, inputs=inputs)

        plan = RacePlanResult(ok=True, result=result, view_model=view_model,
                              session_id=sid, inputs=inputs)
        self._last = plan
        return plan
