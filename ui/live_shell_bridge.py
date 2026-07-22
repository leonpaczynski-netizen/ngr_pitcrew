"""LiveShellBridge — feed the new shell from the running app's real services (F-integration).

The new PitCrewShell renders view-models; this bridge keeps those view-models in
sync with the *real* MainWindow services (event/session/strategy contexts, the active
setup authority, the tracker connection, the Event Command Centre view, and the live
setup on the form). It refreshes on the window's cross-thread signals plus a throttled
timer, and routes the Garage's Apply/Revert back through the window's existing,
already-gated apply path (so the canonical clamp + authority + persistence and every
safety gate are reused, never reimplemented).

Everything is defensive: a failure in any feed must never crash the app or the shell.
The read side (showing real data) is exercised by tests with a duck-typed window; the
write side (Apply/Revert persisting to the car) reuses the classic path and needs
live-rig verification.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, QTimer

from ui.app_state import build_app_state
from ui.new_shell_launch import build_initial_app_state, fetch_guidance_view


class LiveShellBridge(QObject):
    def __init__(self, shell, controller, window=None, config=None, db=None,
                 *, refresh_ms: int = 750, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._controller = controller
        self._window = window
        self._config = config or {}
        self._db = db

        self._timer = QTimer(self)
        self._timer.setInterval(max(200, int(refresh_ms)))
        self._timer.timeout.connect(self.refresh)

        self._wire_signals()
        self._wire_actions()

    # ---- wiring -----------------------------------------------------------
    def _wire_signals(self) -> None:
        """Refresh when the app reports connection / lap / race-state changes."""
        try:
            bridge = getattr(self._window, "bridge", None)
            for sig_name in ("connection_changed", "lap_completed", "race_state_changed",
                             "car_detected", "strategy_status_changed"):
                sig = getattr(bridge, sig_name, None)
                if sig is not None:
                    sig.connect(lambda *_: self.refresh())
        except Exception:
            pass

    def _wire_actions(self) -> None:
        """Route Garage Apply/Revert back through the classic (gated) apply path."""
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is not None:
                gp.apply_requested.connect(self._on_apply)
                gp.revert_requested.connect(self._on_revert)
        except Exception:
            pass

    # ---- lifecycle --------------------------------------------------------
    def start(self) -> None:
        self.refresh()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    # ---- read side (show real data) --------------------------------------
    def refresh(self) -> None:
        """Rebuild the shell's view-models from real services. Never raises."""
        try:
            state = build_initial_app_state(self._window, self._config)
            self._controller.set_state(state)
        except Exception:
            pass
        try:
            view = fetch_guidance_view(self._db, self._config)
            if hasattr(self._shell, "set_guidance_view"):
                self._shell.set_guidance_view(view)
        except Exception:
            pass
        self._feed_garage()
        self._feed_live()

    def _feed_garage(self) -> None:
        """Show the driver's REAL current setup in the Garage GT7 sheet."""
        try:
            gp = getattr(self._shell, "garage_page", None)
            form = getattr(self._window, "_race_form", None)
            if gp is None or form is None or not hasattr(form, "current_setup_dict"):
                return
            setup = form.current_setup_dict()
            label, applied = _active_setup(self._window)
            from ui.setup_recommendation_vm import build_recommendation_vm
            vm = _current_recommendation_vm(self._window)
            gp.set_recommendation(
                vm if vm is not None else build_recommendation_vm({}),
                discipline="race", active_setup=label, applied=applied,
                setup_values=setup,
            )
        except Exception:
            pass

    def _feed_live(self) -> None:
        """Feed the Live Pit Wall from the tracker/session (basic, defensive)."""
        try:
            lp = getattr(self._shell, "live_page", None)
            if lp is None:
                return
            from ui.components.live_pit_wall import LivePitWallVM
            se = None
            try:
                se = self._window._build_session_context()
            except Exception:
                se = None
            connected = bool(getattr(se, "connected", False))
            laps = getattr(se, "laps_recorded", 0) if se is not None else 0
            lp.set_state(LivePitWallVM(
                lap=str(laps) if laps else "—",
                freshness="live" if connected else "none",
                confidence="unknown",
                map_trust="none",
                engineer_instruction="Waiting for live telemetry…" if not connected else "",
            ))
        except Exception:
            pass

    # ---- write side (reuse the classic, gated apply path) ----------------
    def _on_apply(self, field_values: dict) -> None:
        """Apply the shown recommendation via the window's existing apply path.

        Routes the exact {field: value} the driver saw (shown == applied) through the
        classic form apply, which clamps to ranges, updates the active-setup authority
        and persists — reusing every existing safety gate. Never raises.
        """
        try:
            window = self._window
            form = getattr(window, "_race_form", None)
            if not field_values or form is None or not hasattr(form, "apply_ai_fields"):
                return
            form.apply_ai_fields(dict(field_values))
            # Persist via the window's autosave if available.
            saver = getattr(window, "_autosave_applied_setup", None)
            if callable(saver):
                try:
                    saver(form)
                except Exception:
                    pass
            self.refresh()
        except Exception:
            pass

    def _on_revert(self, node_id: str) -> None:
        """Route a lineage revert to the window's revert path. Never raises."""
        try:
            window = self._window
            reverter = getattr(window, "_revert_last_change_for_form", None)
            form = getattr(window, "_race_form", None)
            if callable(reverter) and form is not None:
                reverter(form)
            self.refresh()
        except Exception:
            pass


def _active_setup(window):
    try:
        auth = getattr(window, "_setup_authority", None)
        if auth is None:
            return "", False
        active = auth.active_setup() if hasattr(auth, "active_setup") else None
        if active is None:
            return "", False
        label = getattr(active, "label", "") or getattr(active, "name", "") or ""
        return str(label), bool(getattr(active, "applied", False))
    except Exception:
        return "", False


def _current_recommendation_vm(window):
    """Return the window's most recent recommendation VM, if it has one exposed."""
    try:
        getter = getattr(window, "current_recommendation_vm", None)
        if callable(getter):
            return getter()
    except Exception:
        pass
    return None
