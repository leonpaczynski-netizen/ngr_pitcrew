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
        """Route Garage Apply/Revert/Analyse + Settings save through the classic services."""
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is not None:
                gp.apply_requested.connect(self._on_apply)
                gp.revert_requested.connect(self._on_revert)
                if hasattr(gp, "analyse_requested"):
                    gp.analyse_requested.connect(self._on_analyse)
        except Exception:
            pass
        try:
            sp = getattr(self._shell, "settings_page", None)
            if sp is not None and hasattr(sp, "set_config"):
                sp.set_config(self._config)
                sp.save_requested.connect(self._on_save_settings)
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
        view = None
        try:
            view = fetch_guidance_view(self._db, self._config)
        except Exception:
            view = None
        try:
            if hasattr(self._shell, "set_guidance_view"):
                self._shell.set_guidance_view(view)
        except Exception:
            pass
        self._feed_garage()
        self._feed_qualifying(view)
        self._feed_strategy()
        self._feed_live()
        self._feed_debrief()

    def _connected(self) -> bool:
        try:
            se = self._window._build_session_context() if self._window else None
            return bool(getattr(se, "connected", False))
        except Exception:
            return False

    def _feed_qualifying(self, view) -> None:
        try:
            qp = getattr(self._shell, "qualifying_page", None)
            if qp is None:
                return
            from ui.shell_feed_adapters import qualifying_vm_from_cc_view
            label, _applied = _active_setup(self._window)
            qp.set_readiness(qualifying_vm_from_cc_view(view, active_setup_label=label))
        except Exception:
            pass

    def _feed_strategy(self) -> None:
        try:
            sp = getattr(self._shell, "strategy_page", None)
            if sp is None:
                return
            from ui.shell_feed_adapters import strategy_plan_vm_from_rpvm
            result = getattr(self._window, "_last_race_plan_result", None)
            rpvm = None
            if result is not None:
                try:
                    from ui.race_strategy_vm import build_race_plan_view_model
                    rpvm = build_race_plan_view_model(result)
                except Exception:
                    rpvm = None
            sp.set_plan(strategy_plan_vm_from_rpvm(rpvm))
        except Exception:
            pass

    def _feed_debrief(self) -> None:
        try:
            dp = getattr(self._shell, "debrief_page", None)
            db = self._db
            if dp is None or db is None or not hasattr(db, "build_cross_session_memory"):
                return
            from ui.shell_feed_adapters import debrief_vm_from_memory
            try:
                mem = db.build_cross_session_memory()
            except Exception:
                mem = None
            dp.set_debrief(debrief_vm_from_memory(mem))
        except Exception:
            pass

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
        """Feed the Live Pit Wall from the canonical live race state. Never raises."""
        try:
            lp = getattr(self._shell, "live_page", None)
            if lp is None:
                return
            from ui.shell_feed_adapters import live_pit_wall_vm_from_state
            connected = self._connected()
            state = None
            try:
                tracker = getattr(self._window, "_tracker", None)
                if tracker is not None and getattr(tracker, "race_type", None) is not None:
                    from strategy.canonical_live_race_state import build_canonical_live_race_state
                    canon = build_canonical_live_race_state(tracker, telemetry_fresh=connected)
                    state = canon.to_live_strategy_state()
            except Exception:
                state = None
            lp.set_state(live_pit_wall_vm_from_state(state, connected=connected))
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

    def _on_analyse(self) -> None:
        """Run the setup brain on the current setup via the window's analyse path."""
        try:
            window = self._window
            analyse = getattr(window, "_setup_analyse_ai", None)
            if callable(analyse):
                analyse()
                # the recommendation appears asynchronously; refresh picks it up.
                self.refresh()
        except Exception:
            pass

    def _on_save_settings(self) -> None:
        """Persist the edited config and apply it to the live services. Never raises."""
        sp = getattr(self._shell, "settings_page", None)
        ok = False
        try:
            cfg = sp.apply_to_config() if sp is not None else self._config
            # Persist through the canonical config saver (config-safety aware).
            try:
                import config_paths
                path = getattr(self._window, "config_path", None) or config_paths.resolve_config_path()
                config_paths.save_config(cfg, path)
                ok = True
            except Exception:
                ok = False
            # Apply to the live announcer / tracker where available.
            try:
                announcer = getattr(self._window, "_announcer", None)
                if announcer is not None and hasattr(announcer, "update_config"):
                    announcer.update_config(cfg.get("voice", {}))
            except Exception:
                pass
        except Exception:
            ok = False
        try:
            if sp is not None and hasattr(sp, "show_saved"):
                sp.show_saved(ok)
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
