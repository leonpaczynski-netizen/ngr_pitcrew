"""PitCrewController — the thin QObject that owns the current AppState (F0.3).

The controller holds exactly one immutable ``AppState`` and emits ``state_changed``
whenever it is replaced. The shell chrome (nav rail, event header, progress rail,
guidance card) connects to that one signal and re-renders incrementally — so there
is a single broadcast point for "the world changed", never per-widget polling.

It contains NO engineering logic: it aggregates contexts the caller has already
built (via the existing ``build_*_context`` adapters) into an ``AppState`` through
``ui.app_state.build_app_state``. All validation/immutability lives in AppState.
Emission is de-duplicated — an equal state does not re-fire the signal.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from ui.app_state import AppState, build_app_state


class PitCrewController(QObject):
    #: Fires with the new AppState whenever the state actually changes.
    state_changed = pyqtSignal(object)  # AppState

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._state: AppState = AppState.empty()

    # ---- read ------------------------------------------------------------
    def state(self) -> AppState:
        """The current immutable AppState (never None)."""
        return self._state

    # ---- write -----------------------------------------------------------
    def set_state(self, state: AppState) -> bool:
        """Replace the whole state. Emits ``state_changed`` only if it differs.

        Returns True if the state changed (and the signal fired), else False.
        """
        if not isinstance(state, AppState) or state == self._state:
            return False
        self._state = state
        self.state_changed.emit(state)
        return True

    def patch(self, **changes) -> AppState:
        """Build a new AppState from the current one plus the given overrides.

        Accepts the same keywords as ``build_app_state`` (event, session,
        strategy, active_setup_label, active_setup_applied, programme_stage,
        stage_states, connected). Anything omitted keeps its current value. The
        result is validated by ``build_app_state`` and set via ``set_state`` (so
        an equal result does not re-emit). Returns the resulting state.
        """
        cur = self._state
        new_state = build_app_state(
            event=changes.get("event", cur.event),
            session=changes.get("session", cur.session),
            strategy=changes.get("strategy", cur.strategy),
            active_setup_label=changes.get("active_setup_label", cur.active_setup_label),
            active_setup_applied=changes.get("active_setup_applied", cur.active_setup_applied),
            programme_stage=changes.get("programme_stage", cur.programme_stage),
            stage_states=changes.get("stage_states", dict(cur.stage_states)),
            connected=changes.get("connected", cur.connected),
        )
        self.set_state(new_state)
        return new_state
