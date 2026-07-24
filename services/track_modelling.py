"""Driving the track-modelling workflow, headless (single-system stage 4b).

Holds the ``TrackModellingSession`` and turns a coordinator action into the domain call
that performs it. The domain modules are reused unchanged — this owns no algorithms, only
the sequence and the honesty about what actually happened.

The one rule worth stating: an action is performed ONLY if the coordinator says it is
legal in the current state. The guided page already hides illegal actions, but a service
that trusts its caller is a service that can be driven into an impossible state.

No Qt. Long-running work (capture, build) is synchronous here; the caller decides where
it runs, exactly as the setup engine does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from data.track_modelling_coordinator import (
    TrackModellingAction as A, TrackModellingCoordinator,
)
from data.track_modelling_session import (
    TrackModellingSession, refresh_disk_readiness, session_from_capture,
)


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


@dataclass(frozen=True)
class TrackActionResult:
    ok: bool = False
    reason: str = ""
    action: str = ""
    session: Optional[TrackModellingSession] = None


class TrackModellingService:
    """Performs the guided modelling workflow against the track domain."""

    def __init__(self, *, capture_controller=None, builders: Optional[Dict[str, Callable]] = None):
        self._session = TrackModellingSession()
        self._controller = capture_controller
        #: action name -> callable performing it. Injected so the domain calls can be
        #: supplied by the host (they need the live telemetry stream) and stubbed in tests.
        self._builders = dict(builders or {})

    # ---- read -------------------------------------------------------------
    @property
    def session(self) -> TrackModellingSession:
        return self._session

    def refresh(self) -> TrackModellingSession:
        """Fold live capture state and on-disk readiness into the session."""
        try:
            session = session_from_capture(self._session, self._controller)
            self._session = refresh_disk_readiness(session)
        except Exception:  # pragma: no cover - defensive
            pass
        return self._session

    def can(self, action: str) -> bool:
        try:
            return TrackModellingCoordinator(self._session.to_inputs()).can(A(action))
        except Exception:
            return False

    # ---- write ------------------------------------------------------------
    def select_track(self, location_id: str, layout_id: str) -> TrackActionResult:
        """Choose the circuit and layout. Changing track discards the previous job."""
        loc, lay = _norm(location_id), _norm(layout_id)
        if not loc or not lay:
            return TrackActionResult(reason="Choose both a circuit and a layout.",
                                     action=A.SELECT_TRACK.value, session=self._session)
        self._session = refresh_disk_readiness(self._session.select(loc, lay))
        return TrackActionResult(ok=True, action=A.SELECT_TRACK.value,
                                 session=self._session,
                                 reason=f"{loc} · {lay} selected.")

    def perform(self, action: str) -> TrackActionResult:
        """Perform a coordinator action. Refuses anything illegal in this state."""
        try:
            act = A(_norm(action))
        except ValueError:
            return TrackActionResult(reason="Unknown action.", session=self._session)
        if not self.can(act.value):
            return TrackActionResult(
                action=act.value, session=self._session,
                reason="That is not available at this point in the workflow.")
        handler = getattr(self, f"_do_{act.name.lower()}", None)
        if handler is None:
            runner = self._builders.get(act.value)
            if runner is None:
                return TrackActionResult(
                    action=act.value, session=self._session,
                    reason="That step is not available in this build.")
            return self._run(act, runner)
        return handler(act)

    # ---- individual actions ----------------------------------------------
    def _run(self, act: A, runner: Callable) -> TrackActionResult:
        """Call an injected domain runner and fold its outcome into the session."""
        try:
            outcome = runner(self._session)
        except Exception as exc:
            self._session = self._session.failed(str(exc))
            return TrackActionResult(action=act.value, session=self._session,
                                     reason=str(exc))
        if isinstance(outcome, TrackModellingSession):
            self._session = outcome
            return TrackActionResult(ok=True, action=act.value, session=self._session)
        # A (ok, message, session) tuple is also accepted.
        try:
            ok, message, session = outcome
        except Exception:
            ok, message, session = bool(outcome), "", None
        if isinstance(session, TrackModellingSession):
            self._session = session
        if not ok:
            self._session = self._session.failed(_norm(message))
        return TrackActionResult(ok=bool(ok), action=act.value,
                                 reason=_norm(message), session=self._session)

    def _do_start_capture(self, act: A) -> TrackActionResult:
        try:
            if self._controller is not None and hasattr(self._controller, "start"):
                self._controller.start()
        except Exception as exc:
            self._session = self._session.failed(f"Could not start recording: {exc}")
            return TrackActionResult(action=act.value, session=self._session,
                                     reason=self._session.error_message)
        self._session = self._session.cleared_error().with_(capturing=True)
        return TrackActionResult(ok=True, action=act.value, session=self._session,
                                 reason="Recording — drive clean laps.")

    def _do_stop_capture(self, act: A) -> TrackActionResult:
        try:
            if self._controller is not None and hasattr(self._controller, "stop"):
                self._controller.stop()
        except Exception as exc:
            self._session = self._session.failed(f"Could not stop recording: {exc}")
            return TrackActionResult(action=act.value, session=self._session,
                                     reason=self._session.error_message)
        self._session = self._session.with_(capturing=False, has_captured_laps=True)
        return TrackActionResult(ok=True, action=act.value, session=self._session,
                                 reason="Recording stopped.")

    def _do_reset(self, act: A) -> TrackActionResult:
        self._session = TrackModellingSession()
        return TrackActionResult(ok=True, action=act.value, session=self._session,
                                 reason="Starting again.")

    def _do_clear_track(self, act: A) -> TrackActionResult:
        return self._do_reset(act)

    def _do_recalibrate(self, act: A) -> TrackActionResult:
        """Re-record: keep the track, discard the captured/derived work.

        The artefacts are dropped deliberately — validating a new set of laps against a
        model built from the old ones would report agreement that was never tested.
        """
        session = self._session
        self._session = TrackModellingSession(
            location_id=session.location_id, layout_id=session.layout_id)
        return self._do_start_capture(act)
