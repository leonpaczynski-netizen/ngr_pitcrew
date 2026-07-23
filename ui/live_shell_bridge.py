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
        #: The Garage discipline the driver selected. Owned HERE, not re-derived on
        #: every refresh — the 750ms feed used to force it back to "race", which made
        #: the Base and Qualifying tabs un-selectable.
        self._discipline = "race"
        #: "" or a short description of the long-running Garage job in flight, so a
        #: pressed Analyse/Baseline button is never silent.
        self._pending_work = ""
        #: Which discipline the window's single ``current_recommendation_vm()`` was
        #: produced for. The classic window keeps ONE recommendation VM (whichever
        #: analysis finished last), so the Garage must not show a Race recommendation
        #: under the Qualifying tab — Apply would then write Race deltas into the
        #: Qualifying sheet. "race" is the classic default until we start a run.
        self._rec_discipline = "race"

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
                if hasattr(gp, "discipline_changed"):
                    gp.discipline_changed.connect(self._on_discipline)
                if hasattr(gp, "baseline_requested"):
                    gp.baseline_requested.connect(self._on_build_baseline)
        except Exception:
            pass
        try:
            sp = getattr(self._shell, "settings_page", None)
            if sp is not None and hasattr(sp, "set_config"):
                sp.set_config(self._config)
                sp.save_requested.connect(self._on_save_settings)
        except Exception:
            pass
        # Route every remaining surface action to real behaviour.
        shell = self._shell
        _c = self._safe_connect
        _c(getattr(shell, "run_card", None), "start_requested",
           lambda: self._navigate("live_pit_wall"))
        _c(getattr(shell, "feedback_form", None), "submitted", self._on_feedback)
        _c(getattr(shell, "practice_outcome", None), "action_requested", self._on_outcome_action)
        _c(getattr(shell, "qualifying_page", None), "begin_requested",
           lambda: self._navigate("live_pit_wall"))
        _c(getattr(shell, "strategy_page", None), "approve_requested", self._on_approve_strategy)
        _c(getattr(shell, "debrief_page", None), "action_requested", self._on_debrief_action)
        _c(getattr(shell, "library_page", None), "open_requested", self._on_library_open)
        _c(getattr(shell, "guidance", None), "read_aloud_requested", self._on_read_aloud)
        home = getattr(shell, "home_page", None)
        _c(home, "event_activate_requested", self._on_activate_event)
        _c(home, "manage_events_requested", self._on_manage_events)

    @staticmethod
    def _safe_connect(obj, signal_name, slot) -> None:
        try:
            sig = getattr(obj, signal_name, None)
            if sig is not None:
                sig.connect(slot)
        except Exception:
            pass

    def _navigate(self, dest: str) -> None:
        try:
            nav = getattr(self._shell, "_navigate", None)
            if callable(nav):
                nav(dest)
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
        self._feed_practice()
        self._feed_qualifying(view)
        self._feed_strategy()
        self._feed_live()
        self._feed_debrief()

    def _feed_practice(self) -> None:
        """Feed the Practice run card from the current recommendation (what's being tested)."""
        try:
            rc = getattr(self._shell, "run_card", None)
            if rc is None:
                return
            from ui.shell_feed_adapters import run_card_vm_from_recommendation
            vm = _current_recommendation_vm(self._window)
            label, _applied = _active_setup(self._window)
            rc.set_run(run_card_vm_from_recommendation(vm, active_setup_label=label))
        except Exception:
            pass

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

    def _form_for_discipline(self, discipline: str = ""):
        """The classic setup form that owns this discipline's values.

        The domain has two editable sheets — Race and Qualifying. "Base" is not a
        third sheet: the baseline build FILLS both, so the Base tab reads the Race
        sheet (where the baseline lands) and offers the build action.
        """
        d = (discipline or self._discipline or "race").lower()
        attr = "_qual_form" if d == "qualifying" else "_race_form"
        return getattr(self._window, attr, None)

    def _recommendation_applies_here(self) -> bool:
        """Whether the window's current recommendation belongs to the shown discipline.

        Base and Race share the Race sheet, so a recommendation for one applies to the
        other; Qualifying is a different sheet and never shares.
        """
        pair = {self._rec_discipline, self._discipline}
        return len(pair) == 1 or pair <= {"base", "race"}

    def _on_discipline(self, discipline: str) -> None:
        """Remember the selected discipline and re-feed the Garage for it."""
        d = str(discipline or "").lower()
        if d not in ("base", "qualifying", "race"):
            d = "race"
        self._discipline = d
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is not None and hasattr(gp, "set_status"):
                gp.set_status("")
        except Exception:
            pass
        self._feed_garage()

    def _feed_garage(self) -> None:
        """Show the driver's REAL current setup for the SELECTED discipline."""
        try:
            gp = getattr(self._shell, "garage_page", None)
            form = self._form_for_discipline()
            if gp is None or form is None or not hasattr(form, "current_setup_dict"):
                return
            setup = form.current_setup_dict()
            label, applied = _active_setup(self._window)
            from ui.setup_recommendation_vm import build_recommendation_vm
            vm = _current_recommendation_vm(self._window)
            if not self._recommendation_applies_here():
                vm = None
            # A pending Analyse/Baseline stops being "in progress" the moment a
            # recommendation actually lands — clear the status line then, not before.
            if self._pending_work and vm is not None and vm.proposed_rows():
                self._pending_work = ""
                if hasattr(gp, "set_status"):
                    gp.set_status("")
            gp.set_recommendation(
                vm if vm is not None else build_recommendation_vm({}),
                discipline=self._discipline, active_setup=label, applied=applied,
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
            form = self._form_for_discipline()
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
            form = self._form_for_discipline()
            if callable(reverter) and form is not None:
                reverter(form)
            self.refresh()
        except Exception:
            pass

    def _garage_status(self, text: str) -> None:
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is not None and hasattr(gp, "set_status"):
                gp.set_status(text)
        except Exception:
            pass

    def _on_analyse(self) -> None:
        """Run the setup brain on the current setup via the window's analyse path.

        The analysis runs on a worker thread in the classic window and lands
        asynchronously; the button used to be completely silent while that happened
        (and silent forever when the advisor was unavailable). Report both.
        """
        window = self._window
        # Only report "unavailable" when the window HAS an advisor slot and it is
        # empty — an absent attribute just means an alternate/duck-typed host.
        if hasattr(window, "_driving_advisor") and window._driving_advisor is None:
            self._garage_status(
                "Setup analysis is unavailable — the driving advisor did not load.")
            return
        try:
            if self._discipline == "qualifying":
                fn = getattr(window, "_setup_analyse_ai_for_form", None)
                form = getattr(window, "_qual_form", None)
                started = bool(callable(fn) and form is not None)
                if started:
                    fn(form)
            else:
                fn = getattr(window, "_setup_analyse_ai", None)
                started = callable(fn)
                if started:
                    fn()
        except Exception:
            started = False
        if started:
            self._rec_discipline = self._discipline
            self._pending_work = "analyse"
            self._garage_status(
                "Analysing the current setup… the recommendation appears here when it is ready.")
            self.refresh()
        else:
            self._garage_status("Setup analysis is not available in this build.")

    def _on_build_baseline(self, discipline: str = "") -> None:
        """Build the BASE tune for this event via the classic baseline builder.

        This is the missing "how do I get a base setup" route: it fires the same
        deterministic baseline build the classic Setup Builder uses, which fills BOTH
        the Race and Qualifying sheets from the car ranges + driving profile.
        """
        window = self._window
        fn = getattr(window, "_generate_baseline_setup_both", None)
        if not callable(fn):
            fn = getattr(window, "_generate_baseline_setup", None)
        if not callable(fn):
            self._garage_status("Baseline builder is not available in this build.")
            return
        try:
            fn()
        except Exception:
            self._garage_status("Baseline build could not be started.")
            return
        self._rec_discipline = self._discipline
        self._pending_work = "baseline"
        self._garage_status(
            "Building the baseline setup for the Race and Qualifying sheets…")
        self.refresh()

    # ---- event selection / creation --------------------------------------
    def _on_activate_event(self, event_name: str) -> None:
        """Make a different event the active one, through the classic activation path.

        Reuses ``_on_event_set_active`` so the preparation cycle, strategy fan-out,
        tracker race config and advisor context all follow exactly as they do from the
        Event Planner — this bridge never writes the active event itself.
        """
        name = str(event_name or "").strip()
        window = self._window
        try:
            lst = getattr(window, "_event_list", None)
            if name and lst is not None:
                for row in range(lst.count()):
                    item = lst.item(row)
                    if item is not None and item.text().strip() == name:
                        lst.setCurrentRow(row)
                        break
            fn = getattr(window, "_on_event_set_active", None)
            if callable(fn):
                fn()
            persist = getattr(window, "_persist_config", None)
            if callable(persist):
                persist()
        except Exception:
            pass
        self.refresh()

    def _on_manage_events(self) -> None:
        """Open the classic Event Planner — the full create/edit/delete event editor."""
        try:
            shell = self._shell
            if hasattr(shell, "classic_ui_requested"):
                shell.classic_ui_requested.emit()
            sel = getattr(self._window, "select_tab", None)
            if callable(sel):
                sel("event_planner")
            raise_ = getattr(self._window, "raise_", None)
            if callable(raise_):
                raise_()
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

    # ---- practice / qualifying / strategy / debrief / library actions -----
    def _on_feedback(self, feedback: dict) -> None:
        """Persist structured practice feedback via the window/DB if it supports it."""
        try:
            window = self._window
            for name in ("record_driver_feedback", "_record_driver_feedback", "save_driver_feedback"):
                fn = getattr(window, name, None)
                if callable(fn):
                    fn(dict(feedback or {}))
                    break
            self.refresh()
        except Exception:
            pass

    def _on_outcome_action(self, key: str) -> None:
        """Adaptive practice outcome action -> real behaviour / navigation."""
        try:
            k = (key or "").lower()
            if k == "revert":
                self._on_revert("")
            elif k in ("keep", "build_next", "refine"):
                self._navigate("garage")
            elif k == "to_qualifying":
                self._navigate("qualifying")
            elif k == "gather":
                self._navigate("practice")
            else:
                self._navigate("garage")
        except Exception:
            pass

    def _on_approve_strategy(self) -> None:
        """Approve the (read-only) race plan and move to the live wall. Records approval
        if the window supports it; never mutates a setup."""
        try:
            window = self._window
            fn = getattr(window, "approve_race_plan", None)
            if callable(fn):
                fn()
        except Exception:
            pass
        self._navigate("live_pit_wall")

    def _on_debrief_action(self, key: str) -> None:
        try:
            dest = {"to_qualifying": "qualifying", "to_race": "race_strategy",
                    "prepare_qualifying": "qualifying", "prepare_race": "race_strategy",
                    "continue": "garage", "close": "home", "post_review": "engineering_library"}.get(
                (key or "").lower(), "home")
            self._navigate(dest)
        except Exception:
            pass

    def _on_library_open(self, area: str) -> None:
        """Open the classic engineering panels for the requested Library area."""
        try:
            shell = self._shell
            if hasattr(shell, "classic_ui_requested"):
                shell.classic_ui_requested.emit()
            window = self._window
            sel = getattr(window, "select_tab", None)
            if callable(sel):
                sel("development_history")
        except Exception:
            pass

    def _guidance_status(self, text: str) -> None:
        try:
            g = getattr(self._shell, "guidance", None)
            if g is not None and hasattr(g, "set_status"):
                g.set_status(text)
        except Exception:
            pass

    def _voice_enabled(self) -> bool:
        """Whether voice output is switched on. Unknown config reads as enabled."""
        try:
            return bool((self._config.get("voice") or {}).get("enabled", True))
        except Exception:
            return True

    def _on_read_aloud(self, text: str) -> None:
        """Speak the engineer's message via the existing announcer (opt-in, never forced).

        ``VoiceAnnouncer.announce`` takes (text, priority, cooldown_key) — the previous
        one-argument call raised TypeError into a bare except, so Read aloud was silent.
        A version_key means pressing it twice replaces the queued line instead of
        stacking duplicates.
        """
        text = str(text or "").strip()
        if not text:
            return
        announcer = getattr(self._window, "_announcer", None)
        if announcer is None:
            self._guidance_status("Voice output is not available in this build.")
            return
        if not self._voice_enabled():
            self._guidance_status("Voice is switched off — enable it in Settings to hear this.")
            return
        self._guidance_status("")
        try:
            from telemetry.state import Priority
            announcer.announce(text, Priority.LOW, "shell_read_aloud",
                               cooldown_secs=0.0, interrupt=False,
                               version_key="shell_read_aloud")
            return
        except Exception:
            pass
        # Fallback for a duck-typed/simple announcer (tests, alternate backends).
        for name in ("speak", "say", "enqueue"):
            try:
                fn = getattr(announcer, name, None)
                if callable(fn):
                    fn(text)
                    return
            except Exception:
                continue


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
