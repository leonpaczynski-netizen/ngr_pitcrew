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

    # ---- drive-until-done -------------------------------------------------
    def auto_finalize(self) -> TrackActionResult:
        """Build → validate → activate in one pass, for the drive-until-done flow.

        The driver never approves individual corners: once capture is complete, the model
        is built, geometry-validated and (if it passes) activated automatically. Stops at
        the first step that can't proceed and returns why — the captured work is always
        kept, so a geometry problem just means "keep driving", not "lost your laps".
        """
        build = self.perform("build_model")
        if not build.ok:
            return TrackActionResult(ok=False, action="auto_finalize",
                                     session=self._session,
                                     reason=build.reason or "Could not build the model yet.")
        validate = self.perform("validate")
        if not self._session.validation_passed:
            # ok=True: the model is kept, but it isn't sound enough to approve yet.
            return TrackActionResult(ok=False, action="auto_finalize",
                                     session=self._session,
                                     reason=(validate.reason
                                             or "The model doesn't line up well enough yet."))
        activate = self.perform("activate")
        return TrackActionResult(ok=bool(activate.ok), action="auto_finalize",
                                 session=self._session,
                                 reason=activate.reason or "Track approved.")

    def map_pit_lane(self, pit_lap) -> TrackActionResult:
        """Map the pit lane from one out-lap driven through it.

        The detector finds where the car diverges from the racing line (the reference
        path) and rejoins — it needs the built station map plus the pit lap's samples,
        not the GT7 pit flag. On success the pit-lane boundary is attached to the station
        map and re-exported, so live pit detection, pit loss and pit-window logic use it.
        """
        station_map = self._session.artefact("station_map")
        if station_map is None:
            return TrackActionResult(action="map_pit_lane", session=self._session,
                                     reason="Approve the track model before mapping the pit lane.")
        try:
            from data.track_station_map import (
                detect_pit_lane_from_pit_laps, export_station_map_json)
            boundary = detect_pit_lane_from_pit_laps([pit_lap], station_map)
        except Exception as exc:
            return TrackActionResult(action="map_pit_lane", session=self._session,
                                     reason=f"Could not map the pit lane: {exc}")
        if boundary is None:
            return TrackActionResult(
                action="map_pit_lane", session=self._session,
                reason="I couldn't see the pit lane on that lap — drive in through the "
                       "pit entry, down the lane and back out, then it'll map.")
        try:
            station_map.pit_lane = boundary
            export_station_map_json(station_map)
        except Exception:
            pass
        self._session = self._session.with_artefact("station_map", station_map)
        return TrackActionResult(ok=True, action="map_pit_lane", session=self._session,
                                 reason="Pit lane mapped — the track model is complete.")

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

    def edit_segment(self, row: int, op: str, *, new_name: str = "") -> TrackActionResult:
        """Apply a corner-review edit to the displayed row (``op`` = approve / reject /
        rename / merge / split).

        The edit mutates the in-memory ``review`` artefact and is written to disk only at
        ACTIVATE — exactly as the classic accept defers persistence. Row indices map to the
        SAME geometry-filtered order the review table shows (``geometry_segment_ids``), so
        "the second corner" always resolves to the second row the driver sees.
        """
        from services.track_modelling_pipeline import geometry_segment_ids
        from data import track_segment_review as R

        review = self._session.artefact("review")
        ids = geometry_segment_ids(self._session)
        if review is None or not ids:
            return TrackActionResult(action="edit_segment", session=self._session,
                                     reason="Build the model before reviewing corners.")
        try:
            seg_id = ids[int(row)]
        except (IndexError, ValueError, TypeError):
            return TrackActionResult(action="edit_segment", session=self._session,
                                     reason="That corner is no longer in the list.")

        op = _norm(op).lower()
        name = self._segment_name(review, seg_id)
        if op == "approve":
            R.confirm_segment(review, seg_id)
            reason = f"{name} confirmed."
        elif op == "reject":
            R.reject_segment(review, seg_id)
            reason = f"{name} marked ‘not a corner’ — it won't be used."
        elif op == "rename":
            if not _norm(new_name):
                return TrackActionResult(action="edit_segment", session=self._session,
                                         reason="Enter a name to rename this corner.")
            R.rename_segment(review, seg_id, _norm(new_name))
            reason = f"Renamed to ‘{_norm(new_name)}’."
        elif op == "merge":
            try:
                next_id = ids[int(row) + 1]
            except IndexError:
                return TrackActionResult(
                    action="edit_segment", session=self._session,
                    reason="Nothing after this corner to merge it with.")
            R.merge_segments(review, seg_id, next_id)
            reason = f"Merged {name} with the next corner."
        elif op == "split":
            # A split point can't be picked from the table, so record the intent; the
            # next rebuild acts on it. Honest about what happened rather than silent.
            R.mark_split_required(review, seg_id)
            reason = f"{name} flagged to split — rebuild the model to apply it."
        else:
            return TrackActionResult(action="edit_segment", session=self._session,
                                     reason="Unknown corner action.")
        return TrackActionResult(ok=True, action="edit_segment",
                                 session=self._session, reason=reason)

    @staticmethod
    def _segment_name(review, seg_id: str) -> str:
        for s in getattr(review, "segments", None) or []:
            if getattr(s, "segment_id", "") == seg_id:
                return getattr(s, "display_name", "") or "This corner"
        return "This corner"

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
        # The capture controller is ``TrackCalibrationCaptureController`` — it starts a
        # session with ``start_session(location_id, layout_id)``, NOT a bare ``start()``.
        # The old ``hasattr(self._controller, "start")`` guard was always False, so the
        # controller never recorded and ``refresh()`` immediately reset ``capturing`` to
        # False (the "Start recording does nothing" bug).
        try:
            if self._controller is not None and hasattr(self._controller, "start_session"):
                ok = self._controller.start_session(
                    self._session.location_id, self._session.layout_id)
                if ok is False:
                    reason = (getattr(self._controller, "_error", "")
                              or "Could not start recording.")
                    self._session = self._session.failed(reason)
                    return TrackActionResult(action=act.value, session=self._session,
                                             reason=reason)
        except Exception as exc:
            self._session = self._session.failed(f"Could not start recording: {exc}")
            return TrackActionResult(action=act.value, session=self._session,
                                     reason=self._session.error_message)
        self._session = self._session.cleared_error().with_(capturing=True)
        return TrackActionResult(ok=True, action=act.value, session=self._session,
                                 reason="Recording — drive clean laps.")

    def _do_stop_capture(self, act: A) -> TrackActionResult:
        try:
            if self._controller is not None and hasattr(self._controller, "stop_session"):
                self._controller.stop_session()
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
