"""TrackModellingSession — the modelling job's working state, headless.

Track Modelling is confirmed as a surface that must be CARRIED ACROSS to the new shell,
not retired: not every track is modelled yet, so the driver still needs to model new
ones. This is the same keystone move the setup sheet needed.

Its state currently lives in the classic tab: which location/layout is selected reads
``_tm_location_combo.currentData()``, and whether a station map exists reads
``self._tm_station_map`` on the mixin. ``_tm_build_coordinator_inputs`` then assembles
those widget reads into ``TrackModellingInputs`` for the pure coordinator. So the state
machine is already pure — only the *inputs* to it are trapped in Qt.

This module holds that working state as plain data and derives the coordinator inputs
from it. The pieces underneath were already extracted and are reused unchanged:

  * ``data.track_modelling_coordinator`` — the state machine (pure)
  * ``ui.track_modelling_vm``            — formatting + button states (Qt-free)
  * ``data.track_*``                     — calibration, detection, review, resolver

Pure apart from one optional, explicitly-called disk read (``refresh_disk_readiness``),
which mirrors what the classic tab does today. Never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Optional

from data.track_modelling_coordinator import (
    TrackModellingInputs, TrackModellingState, derive_state,
)


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


#: Capture-controller states that mean laps have been captured but recording has ended.
_CAPTURED_STATES = ("STOPPED", "BUILT")
_RECORDING_STATE = "RECORDING"


def capture_flags(controller: Any, *, restored_session: Any = None) -> tuple:
    """(capturing, has_captured_laps) from a capture controller. Never raises.

    Compared by NAME rather than by importing the enum, so this stays usable without
    the calibration runtime present (tests, and any host that never captures).
    """
    capturing = has_captured = False
    try:
        state = getattr(controller, "_state", None)
        name = _norm(getattr(state, "name", "") or getattr(state, "value", "") or state).upper()
        capturing = name == _RECORDING_STATE
        has_captured = name in _CAPTURED_STATES
    except Exception:  # pragma: no cover - defensive
        capturing = has_captured = False
    if restored_session is not None:
        has_captured = True
    return capturing, has_captured


@dataclass(frozen=True)
class TrackModellingSession:
    """Everything the modelling workflow knows, with no Qt anywhere.

    Replace fields with :meth:`with_` — it is a value, so a stale copy can never be
    mistaken for live state.
    """

    location_id: str = ""
    layout_id: str = ""

    capturing: bool = False
    has_captured_laps: bool = False

    has_reference_path: bool = False
    has_station_map: bool = False
    has_segments: bool = False
    review_complete: bool = False
    validation_passed: bool = False
    model_active: bool = False

    building: bool = False
    error: bool = False
    error_message: str = ""

    #: Opaque handles the workflow carries between steps (station map, review result,
    #: detection result, alignment result). Held, never interpreted here.
    artefacts: dict = field(default_factory=dict)

    # ---- derived ----------------------------------------------------------
    @property
    def identity_known(self) -> bool:
        return bool(self.location_id and self.layout_id)

    def to_inputs(self) -> TrackModellingInputs:
        """The coordinator's external truth — previously assembled from widget reads."""
        return TrackModellingInputs(
            identity_known=self.identity_known,
            capturing=self.capturing,
            has_captured_laps=self.has_captured_laps,
            has_reference_path=self.has_reference_path,
            has_station_map=self.has_station_map,
            has_segments=self.has_segments,
            review_complete=self.review_complete,
            validation_passed=self.validation_passed,
            model_active=self.model_active,
            building=self.building,
            error=self.error,
        )

    @property
    def state(self) -> TrackModellingState:
        return derive_state(self.to_inputs())

    # ---- transform --------------------------------------------------------
    def with_(self, **changes) -> "TrackModellingSession":
        """A new session with the given fields replaced. Unknown keys are ignored."""
        known = {k: v for k, v in changes.items()
                 if k in TrackModellingSession.__dataclass_fields__}
        return replace(self, **known) if known else self

    def select(self, location_id: str, layout_id: str) -> "TrackModellingSession":
        """Select a track. Changing track CLEARS the previous job's working state —
        carrying a station map from one layout onto another would silently model the
        wrong circuit."""
        loc, lay = _norm(location_id), _norm(layout_id)
        if loc == self.location_id and lay == self.layout_id:
            return self
        return TrackModellingSession(location_id=loc, layout_id=lay)

    def with_artefact(self, name: str, value) -> "TrackModellingSession":
        """Attach a workflow artefact and set the flag that depends on it."""
        arte = dict(self.artefacts)
        arte[_norm(name)] = value
        flag = {
            "station_map": "has_station_map",
            "reference_path": "has_reference_path",
            "detection": "has_segments",
        }.get(_norm(name))
        changes = {"artefacts": arte}
        if flag:
            changes[flag] = value is not None
        return replace(self, **changes)

    def artefact(self, name: str):
        return self.artefacts.get(_norm(name))

    def failed(self, message: str) -> "TrackModellingSession":
        return replace(self, error=True, error_message=_norm(message), building=False)

    def cleared_error(self) -> "TrackModellingSession":
        return replace(self, error=False, error_message="")


def session_from_capture(
    session: TrackModellingSession,
    controller: Any,
    *,
    restored_session: Any = None,
) -> TrackModellingSession:
    """Fold a capture controller's state into the session. Never raises."""
    capturing, has_captured = capture_flags(controller, restored_session=restored_session)
    return session.with_(capturing=capturing, has_captured_laps=has_captured)


def refresh_disk_readiness(session: TrackModellingSession) -> TrackModellingSession:
    """Fold the on-disk readiness for the selected track into the session.

    The one deliberate I/O touch, mirroring what the classic tab does on selection.
    An approved model on disk is what lets a known track land straight in ACTIVE
    instead of asking the driver to re-model it.
    """
    if not session.identity_known:
        return session
    try:
        from data.track_readiness_disk import resolve_track_readiness_from_disk
        rr = resolve_track_readiness_from_disk(session.location_id, session.layout_id)
        approved = bool(getattr(rr, "is_approved", False))
    except Exception:
        return session
    return session.with_(model_active=approved,
                         validation_passed=approved or session.validation_passed)
