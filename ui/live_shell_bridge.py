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

from typing import Mapping, Optional

import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ui.app_state import build_app_state
from ui.new_shell_launch import build_initial_app_state, fetch_guidance_view


#: Garage discipline -> the setup-authority purpose that scopes the active setup.
_PURPOSE = {"race": "Race", "qualifying": "Qualifying"}

#: Library area -> (classic tab key to host natively, detail title, note when absent).
#: Every engineering area lives in the Development History tab's sub-tabs today, so
#: they all resolve there; History and Telemetry have their own pages.
_LIBRARY_TAB = {
    "development_history": ("development_history", "Development History", ""),
    "evidence_provenance": ("development_history", "Evidence & Provenance", ""),
    "rule_traces": ("development_history", "Rule Traces", ""),
    "knowledge_graph": ("development_history", "Knowledge Graph", ""),
    "readiness_assurance": ("development_history", "Readiness & Assurance", ""),
    "certification": ("development_history", "Certification", ""),
    "uat": ("development_history", "Bench & Manual UAT", ""),
    "season_knowledge": ("development_history", "Season & Knowledge", ""),
}


class LiveShellBridge(QObject):
    #: Emitted from the setup workers so results are handled on the Qt thread —
    #: a worker must never touch a widget.
    _analysis_done = pyqtSignal(object)
    _baseline_done = pyqtSignal(object)
    _plan_done = pyqtSignal(object)

    def __init__(self, shell, controller, window=None, config=None, db=None,
                 *, refresh_ms: int = 750, parent=None, spawn=None):
        super().__init__(parent)
        #: How long-running setup work is started. INJECTABLE: the engine is synchronous
        #: by design and only this bridge decides where it runs. Tests pass an inline
        #: runner — a real thread emitting into a QObject under teardown aborts the
        #: process, and inline keeps the assertions deterministic.
        self._spawn = spawn or (
            lambda fn: threading.Thread(target=fn, daemon=True).start())
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
        #: The write side of the guided practice loop. Without it, nothing the driver
        #: does in a run ever reaches the event programme, so the engineer never moves.
        from ui.practice_run_recorder import PracticeRunRecorder
        self._runs = PracticeRunRecorder(db=db, config=self._config)
        # Event create/edit/activate, headless — no classic Event Planner involved.
        from services.event_setup import EventSetupService
        self._events = EventSetupService(
            db=db, config=self._config,
            persist=getattr(window, "_persist_config", None))
        # The setup engine, headless: the store owns the working sheets and the service
        # performs build/analyse/apply/revert/confirm without touching a widget.
        from services.setup_inputs import build_setup_inputs
        from services.setup_service import SetupService
        from services.setup_store import SetupSheetStore, default_store_path
        from services.setup_history_store import SetupHistoryStore, default_history_path
        _cfg_path = str(getattr(window, "config_path", "") or "")
        self._sheets = SetupSheetStore(default_store_path(_cfg_path))
        # Persisted applied-revision history: fills the Garage Lineage tab and lets a
        # past setup be loaded back ("the settings I'm running in GT7").
        self._setup_history = SetupHistoryStore(default_history_path(_cfg_path))
        self._setups = SetupService(
            store=self._sheets, advisor=getattr(window, "_driving_advisor", None),
            authority=getattr(window, "_setup_authority", None), db=db,
            history=self._setup_history,
            inputs_provider=lambda: build_setup_inputs(db, self._config))
        # Track modelling, headless and guided. Reuses the domain untouched; the
        # coordinator decides which actions are legal at each point.
        # Race plan, headless — the strategy page could previously only DISPLAY a plan
        # the classic tab had built, so in the new shell it stayed empty forever.
        from services.race_plan import RacePlanService
        self._plans = RacePlanService(db=db, config=self._config)
        self._plan_done.connect(self._on_plan_done)
        from services.track_modelling import TrackModellingService
        self._tracks = TrackModellingService(
            capture_controller=getattr(window, "_tm_controller", None))
        #: Scopes already seeded from the classic sheets — see ``_seed_sheets``.
        self._seeded: set = set()
        #: The last AnalysisResult (it carries the discipline it belongs to).
        self._last_analysis = None
        self._analysis_done.connect(self._on_analysis_done)
        self._baseline_done.connect(self._on_baseline_done)
        #: Last Event Command Centre view — the run planner reads the current objective
        #: from it so a started run carries the purpose the engineer actually asked for.
        self._last_guidance_view = None
        #: (key, index, label, widget) of a classic tab page currently hosted natively.
        self._borrowed = None
        #: session_id -> RunReview, so the 750ms feed does not re-summarise every tick.
        self._review_cache = {}
        #: The session bound by the most recent "End run & record". A FALLBACK only —
        #: which runs count is resolved from the programme (see ``_recorded_pair``), so
        #: the run-to-run comparison survives a restart instead of resetting to "this is
        #: the first recorded run for this setup" every launch.
        self._last_recorded_session_id = 0
        #: The previous recorded run's session id, for the outcome comparison.
        self._previous_recorded_session_id = 0
        #: Runs bound to the active cycle, resolved once per refresh tick.
        self._runs_cache = None
        #: Track pickers are filled once — the circuit list does not change at runtime.
        self._track_choices_loaded = False

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
                if hasattr(gp, "tyre_change_requested"):
                    gp.tyre_change_requested.connect(self._on_tyre_change)
                if hasattr(gp, "shift_rpm_changed"):
                    gp.shift_rpm_changed.connect(self._on_shift_rpm_changed)
                if hasattr(gp, "shift_rpm_recommend_requested"):
                    gp.shift_rpm_recommend_requested.connect(self._on_shift_rpm_recommend)
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
        rc = getattr(shell, "run_card", None)
        _c(rc, "start_requested", self._on_start_run)
        _c(rc, "record_requested", self._on_record_run)
        _c(rc, "discard_requested", self._on_discard_run)
        _c(getattr(shell, "garage_page", None), "applied_in_game_confirmed",
           self._on_applied_in_game)
        _c(getattr(shell, "feedback_form", None), "submitted", self._on_feedback)
        _c(getattr(shell, "practice_outcome", None), "action_requested", self._on_outcome_action)
        _c(getattr(shell, "qualifying_page", None), "begin_requested",
           lambda: self._navigate("live_pit_wall"))
        _c(getattr(shell, "strategy_page", None), "approve_requested", self._on_approve_strategy)
        _c(getattr(shell, "strategy_page", None), "build_requested", self._on_build_plan)
        _c(getattr(shell, "debrief_page", None), "action_requested", self._on_debrief_action)
        _c(getattr(shell, "library_page", None), "open_requested", self._on_library_open)
        _c(getattr(shell, "library_page", None), "back_requested", self._return_classic_tab)
        tmp = getattr(shell, "track_model_page", None)
        _c(tmp, "track_selected", self._on_track_selected)
        _c(tmp, "action_requested", self._on_track_action)
        _c(getattr(shell, "programme_page", None), "start_next_requested",
           self._on_programme_start_next)
        _c(getattr(shell, "guidance", None), "read_aloud_requested", self._on_read_aloud)
        home = getattr(shell, "home_page", None)
        _c(home, "event_activate_requested", self._on_activate_event)
        _c(home, "manage_events_requested", self._on_manage_events)
        esp = getattr(shell, "event_setup_page", None)
        _c(esp, "save_requested", self._on_event_draft_saved)
        _c(esp, "edit_requested", self._on_event_draft_open)

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
        # The recorded-run list is read several times per tick (which run to review,
        # what kind it was, what to compare it against). Resolve it ONCE per refresh so
        # the 750 ms feed stays at one bounded query rather than three.
        self._runs_cache = None
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
        # Keep the last GOOD view: a transient fetch failure must not blank the
        # engineer's objective (which is what the run card and run planner read).
        if view is not None:
            self._last_guidance_view = view
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
        self._feed_track_model()
        self._feed_programme(view)

    def _feed_practice(self) -> None:
        """Feed the Practice run card from the current recommendation + the open run."""
        try:
            rc = getattr(self._shell, "run_card", None)
            if rc is None:
                return
            from ui.shell_feed_adapters import run_card_vm_from_recommendation
            vm = self._recommendation_vm()
            label, _applied = self._setups.active_setup(self._discipline)
            card = run_card_vm_from_recommendation(vm, active_setup_label=label)
            if not card.has_plan:
                # No setup recommendation to validate does NOT mean no run to do — the
                # engineer's own objective IS the run's purpose. Without this the driver
                # was sent to Practice by "Start a coaching run" and found a blank page
                # with no way to start anything.
                card = self._objective_run_card(label)
            rc.set_run(card)
            # Show the OPEN run (if any) with its live lap count, so the driver can see
            # the run is being captured and knows it still has to be ended to count.
            run = self._runs.open_run()
            if run:
                rc.set_recording(str(run.get("title") or "Practice run"),
                                 self._live_lap_count(), connected=self._connected())
            else:
                rc.set_recording("")
        except Exception:
            pass
        self._feed_run_review()

    def _feed_run_review(self) -> None:
        """Show the laps of the run being reviewed — measured truth, not memory."""
        try:
            panel = getattr(self._shell, "run_laps", None)
            if panel is None:
                return
            panel.set_review(self._review_for(self._review_session_id()))
            from strategy.run_brief import brief_for_run_type
            run_type = self._recorded_run_domain()
            if run_type:
                brief = brief_for_run_type(run_type)
                panel.set_run_kind(brief.run_name, brief.reports)
            else:
                panel.set_run_kind("")
        except Exception:
            pass

    def _review_session_id(self):
        """The session the Review tab is about: the live one, else the last recorded."""
        sid = self._live_session_id()
        if sid:
            return sid
        last, _prev = self._recorded_pair()
        return last

    def _recorded_runs(self) -> list:
        """The runs bound to this event, cached for the duration of one refresh tick."""
        if self._runs_cache is None:
            try:
                self._runs_cache = list(self._runs.recorded_runs())
            except Exception:
                self._runs_cache = []
        return self._runs_cache

    def _recorded_pair(self):
        """(last recorded session, the one before it) for this event — 0 when absent.

        Resolved from the runs actually BOUND to the active preparation cycle, so the
        comparison survives a restart. The in-memory ids are kept only as a fallback for
        the moment between binding a run and the programme read catching up.
        """
        runs = self._recorded_runs()
        ids = [int(r.get("session_id") or 0) for r in runs if int(r.get("session_id") or 0) > 0]
        if len(ids) >= 2:
            return ids[-1], ids[-2]
        if len(ids) == 1:
            return ids[0], self._previous_recorded_session_id
        return self._last_recorded_session_id, self._previous_recorded_session_id

    def _recorded_run_domain(self) -> str:
        """The activity type of the run being reviewed, as a domain-ish key ("" unknown).

        Lets the Review report against what the run was actually FOR instead of
        rendering the same generic summary whatever the driver was sent out to do.
        """
        sid = int(self._review_session_id() or 0)
        if sid:
            for r in self._recorded_runs():
                if int(r.get("session_id") or 0) == sid:
                    return str(r.get("activity_type") or "")
        # A run still open (being driven now) is described by the activity itself.
        try:
            run = self._runs.open_run() or {}
            return str(run.get("activity_type") or "")
        except Exception:
            return ""

    def _review_for(self, session_id):
        """Build a RunReview for a session id (cached per id so the 750ms feed is cheap)."""
        from strategy.practice_run_review import RunReview, build_run_review
        sid = int(session_id or 0)
        if not sid or self._db is None or not hasattr(self._db, "get_session_laps"):
            return RunReview()
        cached = self._review_cache.get(sid)
        laps = None
        try:
            laps = self._db.get_session_laps(sid)
        except Exception:
            laps = None
        if laps is None:
            return cached or RunReview()
        if cached is not None and len(cached.laps) == len([
                r for r in laps if int((r or {}).get("lap_time_ms") or 0) > 0]):
            return cached
        review = build_run_review(laps)
        self._review_cache[sid] = review
        return review

    def _objective_run_card(self, setup_label: str = ""):
        """A run card built from the engineer's current objective.

        Most objectives are not "validate this setup change" — they are "go and gather
        <domain> evidence", and that is a perfectly good run plan. The card describes the
        run the objective asks for so it can actually be started.

        The content comes from ``strategy.run_brief``: each domain is served by a
        genuinely different kind of run, and the card now says how to drive THIS one,
        what to watch, and what the review will report. It previously emitted the same
        template for every domain — including the placeholder monitor line "whatever the
        coaching run is meant to show" — so a coaching run was indistinguishable from
        every other run the programme asked for.
        """
        from ui.components.run_card import RunCardVM
        from strategy.practice_run_recording import domain_from_objective_headline
        from strategy.run_brief import brief_for_domain
        view = self._last_guidance_view if isinstance(self._last_guidance_view, dict) else {}
        na = view.get("next_action") or {}
        headline = str(na.get("headline") or "")
        detail = str(na.get("detail") or "")
        domain = domain_from_objective_headline(headline)
        if not domain:
            return RunCardVM()
        brief = brief_for_domain(domain)
        return RunCardVM(
            objective=brief.objective,
            setup_label=setup_label,
            expected_effect=detail,
            how_to_drive=brief.how_to_drive,
            monitor=brief.monitor,
            reports=brief.reports,
            fuel=brief.fuel,
            tyre=brief.tyre,
            purpose=brief.purpose,
            target_laps=brief.target_laps,
            push_level=brief.push_level,
            invalidation=brief.invalidation,
        )

    def _live_session_id(self):
        """The telemetry session currently being recorded (0 when none)."""
        try:
            return int(getattr(getattr(self._window, "_dispatcher", None), "_session_id", 0) or 0)
        except Exception:
            return 0

    def _live_lap_count(self) -> int:
        try:
            meta = self._db.get_session_meta(self._live_session_id()) if self._db else None
            return int((meta or {}).get("total_laps") or 0)
        except Exception:
            return 0

    # ---- guided practice loop (the write side) ---------------------------
    def _run_status(self, text: str) -> None:
        try:
            rc = getattr(self._shell, "run_card", None)
            if rc is not None and hasattr(rc, "set_status"):
                rc.set_status(text)
        except Exception:
            pass

    def _on_start_run(self) -> None:
        """Open a preparation activity for this run, then go to the pit wall.

        The run's PURPOSE comes from the engineer's current objective — that is what
        decides which evidence domains the run can contribute to once it is recorded.
        """
        from strategy.practice_run_recording import domain_from_objective_headline
        view = self._last_guidance_view if isinstance(self._last_guidance_view, dict) else {}
        na = view.get("next_action") or {}
        headline = str(na.get("headline") or "")
        plan = self._runs.start_run(
            objective_domain=domain_from_objective_headline(headline),
            objective_headline=headline)
        if not plan.ok:
            self._run_status(plan.reason or "Could not start the run.")
            return
        self._run_status("Run open — drive it, then come back and press “End run & record”."
                         if not plan.reused else "That run is already open.")
        self.refresh()
        self._navigate("live_pit_wall")

    def _on_record_run(self) -> None:
        """Bind the completed telemetry session to the open run — the ONE explicit
        action that turns laps into event evidence."""
        sid = self._live_session_id()
        decision = self._runs.record_run(sid)
        if not decision.ok:
            self._run_status(decision.reason or "Could not record the run.")
            return
        # Keep the recorded run reviewable after the live session moves on, and keep the
        # one before it so the next outcome has something to compare against.
        if self._last_recorded_session_id != int(decision.session_id or 0):
            self._previous_recorded_session_id = self._last_recorded_session_id
        self._last_recorded_session_id = int(decision.session_id or 0)
        msg = (f"Run recorded — {decision.reason} "
               f"Open Review to see the laps, then submit your feedback.")
        if decision.warning:
            msg += f"  ⚠ {decision.warning}"
        self._run_status(msg)
        self._feed_run_review()
        self._feed_outcome()
        self.refresh()

    def _on_discard_run(self) -> None:
        ok = self._runs.discard_run()
        self._run_status("Run discarded — nothing was recorded against the event."
                         if ok else "There was no open run to discard.")
        self.refresh()

    def _on_applied_in_game(self, discipline: str = "") -> None:
        """Register that the driver typed this sheet into GT7.

        Applying a recommendation only writes the SHEET; GT7 can only be updated by the
        driver. This confirmation is therefore the ONLY thing that can make a setup
        active — nothing is able to infer it.
        """
        import time
        outcome = self._setups.confirm_applied_in_game(
            discipline or self._discipline,
            applied_at=time.strftime("%Y-%m-%d %H:%M"))
        self._garage_status(outcome.reason)
        self.refresh()

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
            label, _applied = self._setups.active_setup("qualifying")
            qp.set_readiness(qualifying_vm_from_cc_view(view, active_setup_label=label))
        except Exception:
            pass

    def _feed_strategy(self) -> None:
        try:
            sp = getattr(self._shell, "strategy_page", None)
            if sp is None:
                return
            from ui.shell_feed_adapters import strategy_plan_vm_from_rpvm
            plan = self._plans.last_plan
            rpvm = plan.view_model if (plan is not None and plan.ok) else None
            if rpvm is None:
                # Fall back to a plan the classic tab built, so an existing one is not
                # lost while both surfaces exist. Removed with the classic UI.
                result = getattr(self._window, "_last_race_plan_result", None)
                if result is not None:
                    try:
                        from ui.race_strategy_vm import build_race_plan_view_model
                        rpvm = build_race_plan_view_model(result)
                    except Exception:
                        rpvm = None
            sp.set_plan(strategy_plan_vm_from_rpvm(rpvm))
        except Exception:
            pass

    def _feed_track_model(self) -> None:
        """Render the guided modelling flow from the live session."""
        try:
            page = getattr(self._shell, "track_model_page", None)
            if page is None:
                return
            if not self._track_choices_loaded:
                self._track_choices_loaded = True
                page.set_tracks(*_track_choices())
            page.set_session(self._tracks.refresh())
        except Exception:
            pass

    def _on_track_selected(self, location_id: str, layout_id: str) -> None:
        result = self._tracks.select_track(location_id, layout_id)
        self._feed_track_model()
        if not result.ok:
            self._track_status(result.reason)

    def _on_track_action(self, action: str) -> None:
        result = self._tracks.perform(action)
        self._feed_track_model()
        if not result.ok and result.reason:
            self._track_status(result.reason)

    def _track_status(self, text: str) -> None:
        try:
            page = getattr(self._shell, "track_model_page", None)
            if page is not None:
                page._detail.setText(text)
                page._detail.setVisible(bool(text))
        except Exception:
            pass

    def _feed_programme(self, view) -> None:
        """Show where the driver is in the WHOLE event programme.

        Reads the readiness the Command Centre already produced — how many qualifying
        runs each evidence area has and needs — and the current objective's domain, so
        the map can flag which area is live. Adds no new authority; it only makes the
        progress the domain already computed visible, which is what "going in circles"
        was really missing.
        """
        try:
            page = getattr(self._shell, "programme_page", None)
            if page is None:
                return
            from strategy.programme_map import build_programme_map
            from strategy.practice_run_recording import domain_from_objective_headline
            # Prefer whichever view actually carries readiness — the freshly-fetched one
            # normally, but the last good view when this tick's fetch was thin (the run
            # planner reads _last_guidance_view for the same reason).
            v = view if (isinstance(view, Mapping) and view.get("readiness")) else None
            if v is None:
                v = self._last_guidance_view if isinstance(self._last_guidance_view, Mapping) else {}
            readiness = v.get("readiness") or []
            na = v.get("next_action") or {}
            next_domain = str(na.get("domain") or "").strip().lower() \
                or domain_from_objective_headline(str(na.get("headline") or ""))
            page.set_map(build_programme_map(readiness, next_domain=next_domain))
        except Exception:
            pass

    def _on_programme_start_next(self, domain: str) -> None:
        """Start the run the programme map points at — the weakest area's run type."""
        from strategy.run_brief import brief_for_domain
        brief = brief_for_domain(domain)
        if self._runs.open_run() is not None:
            self._show_run_card()
            self._run_status("A run is already open — drive it, then press “End run & record”.")
            return
        plan = self._runs.start_run(objective_domain=brief.domain,
                                    objective_headline=brief.objective)
        self._show_run_card()
        if not plan.ok:
            self._run_status(plan.reason or "Could not start the run.")
            return
        self._run_status(
            f"A {brief.run_name} is open — drive it, then press “End run & record”. "
            f"That is the run this area of the programme needs.")
        self.refresh()

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

        The domain has exactly two editable sheets — Race and Qualifying. The initial
        setup build FILLS both; it is an action, not a third sheet.
        """
        d = (discipline or self._discipline or "race").lower()
        attr = "_qual_form" if d == "qualifying" else "_race_form"
        return getattr(self._window, attr, None)

    def _recommendation_vm(self):
        """The recommendation VM for the SHOWN discipline, or None.

        Race and Qualifying are separate sheets and never share a recommendation —
        rendering one on the other would let Apply write the wrong deltas.
        """
        result = self._last_analysis
        if result is None or result.discipline != self._discipline:
            return None
        if not result.has_recommendation:
            return None
        try:
            from ui.setup_recommendation_vm import build_recommendation_vm
            return build_recommendation_vm({
                "status": result.status or "approved",
                "analysis": result.analysis,
                "changes": list(result.changes),
                "setup_fields": dict(result.setup_fields),
            })
        except Exception:
            return None

    def _seed_sheets(self) -> None:
        """Copy an in-progress classic setup into the store ONCE, per scope.

        The store is the source of truth now, but the driver may already have a setup
        sitting in the classic form from before the switch. It is copied across the
        first time a scope is seen, and only where the store holds nothing authored —
        an existing sheet is never overwritten by a stale form.
        """
        try:
            inputs = self._setups.inputs()
            scope = inputs.scope
            if not inputs.is_known or scope in self._seeded:
                return
            self._seeded.add(scope)
            from strategy.setup_sheet import sheet_from_dict
            for discipline, attr in (("race", "_race_form"), ("qualifying", "_qual_form")):
                if self._sheets.has_setup(scope, discipline):
                    continue
                form = getattr(self._window, attr, None)
                try:
                    values = form.current_setup_dict() if form is not None else None
                except Exception:
                    values = None
                if not values:
                    continue
                sheet = sheet_from_dict(values)
                if sheet.is_authored:
                    self._sheets.set(scope, discipline, sheet)
        except Exception:
            pass

    def _mirror_to_classic(self, discipline: str = "") -> None:
        """Keep the classic form showing what the store holds.

        TRANSITIONAL, removed with the classic window in stage 6: while that window can
        still be opened it must not display numbers that disagree with the real sheet.
        """
        try:
            form = self._form_for_discipline(discipline)
            if form is None or not hasattr(form, "apply_ai_fields"):
                return
            form.apply_ai_fields(self._setups.sheet(discipline or self._discipline).as_dict())
        except Exception:
            pass

    def _feed_garage(self) -> None:
        """Show the driver's REAL current setup for the SELECTED discipline."""
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is None:
                return
            self._seed_sheets()
            sheet = self._setups.sheet(self._discipline)
            # A defaults-only sheet is NOT a setup. Passing it would present numbers
            # nobody authored as though they were the driver's own.
            setup = sheet.as_dict() if sheet.is_authored else None
            label, applied = self._setups.active_setup(self._discipline)
            from ui.setup_recommendation_vm import build_recommendation_vm
            vm = self._recommendation_vm()
            gp.set_recommendation(
                vm if vm is not None else build_recommendation_vm({}),
                discipline=self._discipline, active_setup=label, applied=applied,
                setup_values=setup,
                lineage_nodes=self._lineage_nodes(label),
                has_recorded_run=self._has_recorded_run(),
            )
            self._feed_tyres(gp, setup or {})
            self._feed_shift_rpm(gp)
        except Exception:
            pass

    def _lineage_nodes(self, active_label: str = ""):
        """Build the Garage lineage from the recorded applied revisions (newest first).

        Each confirmed revision is a node; the summary is what changed from the previous
        revision, so the driver can see how the setup evolved. The newest revision is the
        current one; older ones offer "Load this setup". The tab was blank because nothing
        ever fed it — the history now does.
        """
        from ui.components.setup_lineage import LineageNode
        from strategy.setup_sheet import sheet_from_dict
        revs = self._setups.revisions(self._discipline)
        if not revs:
            return ()
        nodes = []
        newest_rev = max(int(r.get("revision") or 0) for r in revs)
        prev_sheet = None
        ordered = sorted(revs, key=lambda r: int(r.get("revision") or 0))
        summaries = {}
        for r in ordered:
            cur_sheet = sheet_from_dict(r.get("fields") or {})
            if prev_sheet is not None:
                changed = tuple(sorted(prev_sheet.diff(cur_sheet)))
                summaries[int(r.get("revision") or 0)] = (
                    "Changed " + ", ".join(changed[:4]) + ("…" if len(changed) > 4 else "")
                    if changed else "No tuning change")
            else:
                summaries[int(r.get("revision") or 0)] = "Baseline"
            prev_sheet = cur_sheet
        for r in sorted(revs, key=lambda r: int(r.get("revision") or 0), reverse=True):
            rev = int(r.get("revision") or 0)
            nodes.append(LineageNode(
                node_id=f"rev{rev}",
                label=str(r.get("label") or f"Setup · rev {rev}"),
                is_current=(rev == newest_rev),
                summary=summaries.get(rev, ""),
                discipline=self._discipline,
                revertable=True))
        return tuple(nodes)

    def _feed_shift_rpm(self, garage) -> None:
        """Show the upshift point for the selected discipline.

        The sheet is authoritative; when it has none yet, the driver's existing global
        config value for this discipline is shown so nothing they already set disappears.
        """
        try:
            if not hasattr(garage, "set_shift_rpm"):
                return
            rpm = self._setups.shift_rpm(self._discipline)
            source = "this setup"
            if rpm <= 0:
                rpm = self._config_shift_rpm(self._discipline)
                source = "your saved setting" if rpm > 0 else ""
            if rpm > 0:
                note = (f"The beep fires at {rpm} RPM in a "
                        f"{'race' if self._discipline == 'race' else 'qualifying'} "
                        f"session (from {source}).")
            else:
                note = ("No shift point yet — set one, or press “Recommend from car” "
                        "after driving so GT7 has broadcast its indicator.")
            garage.set_shift_rpm(rpm, note)
        except Exception:
            pass

    def _on_discipline(self, discipline: str) -> None:
        """Remember the selected discipline and re-feed the Garage for it."""
        d = str(discipline or "").lower()
        if d not in ("qualifying", "race"):
            d = "race"
        self._discipline = d
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is not None and hasattr(gp, "set_status"):
                gp.set_status("")
        except Exception:
            pass
        self._feed_garage()

    def _feed_tyres(self, garage, setup) -> None:
        """Offer the compounds this event's regulations allow for this discipline."""
        try:
            if not hasattr(garage, "set_tyre_choice"):
                return
            from strategy.tyre_selection import build_tyre_choice, current_code
            ev = None
            try:
                ev = self._window._build_event_context()
            except Exception:
                ev = None
            garage.set_tyre_choice(
                build_tyre_choice(
                    discipline=self._discipline,
                    available=getattr(ev, "available_tyres", ()) or (),
                    required=getattr(ev, "required_tyres", ()) or (),
                    race_duration_minutes=float(getattr(ev, "race_duration_minutes", 0) or 0)),
                current_code(setup))
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
    def _has_recorded_run(self) -> bool:
        """Whether any practice run has been recorded against the active event.

        Analyse reads how a setup BEHAVED, so it only becomes available once there is a
        recorded run to read.
        """
        try:
            cid = self._runs.active_cycle_id()
            if not cid or self._db is None or not hasattr(self._db, "get_practice_sessions_for_cycle"):
                return False
            return bool(self._db.get_practice_sessions_for_cycle(cid))
        except Exception:
            return False

    def _on_tyre_change(self, code: str) -> None:
        """Put a different compound on the car, through the setup engine."""
        from strategy.tyre_selection import setup_fields_for
        fields = setup_fields_for(code)
        if not fields:
            self._garage_status("That compound is not recognised.")
            return
        outcome = self._setups.apply(self._discipline, fields)
        if not outcome.ok:
            self._garage_status(outcome.reason or "Could not change the tyres.")
            return
        self._mirror_to_classic(self._discipline)
        self._garage_status(
            f"{fields['tyre_front']} on the {self._discipline} sheet — "
            f"set it in GT7, then press “I've entered this in GT7”.")
        self.refresh()

    # ---- shift beep -------------------------------------------------------
    def _config_shift_rpm(self, discipline: str) -> int:
        """The saved global RPM for a discipline (the fallback before a sheet has one)."""
        try:
            sb = self._config.get("shift_beep", {}) if isinstance(self._config, dict) else {}
            key = "race_rpm" if str(discipline).lower() == "race" else "qual_rpm"
            return int(sb.get(key) or sb.get("rpm", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _project_shift_rpm_to_config(self) -> None:
        """Mirror each sheet's shift point into config so the live beep uses it.

        The beep loop in main.py already picks race_rpm vs qual_rpm by the session being
        driven; making config a projection of the sheets means the beep follows the setup
        loaded for that discipline with NO change to the beep loop. A sheet with no shift
        point (0) never clears an existing saved value.
        """
        try:
            if not isinstance(self._config, dict):
                return
            sb = self._config.setdefault("shift_beep", {})
            changed = False
            for discipline, key in (("race", "race_rpm"), ("qualifying", "qual_rpm")):
                rpm = self._setups.shift_rpm(discipline)
                if rpm > 0 and int(sb.get(key, 0) or 0) != rpm:
                    sb[key] = rpm
                    changed = True
            if changed:
                self._persist_config()
        except Exception:
            pass

    def _persist_config(self) -> None:
        try:
            import config_paths
            path = getattr(self._window, "config_path", None) or config_paths.resolve_config_path()
            config_paths.save_config(self._config, path)
        except Exception:
            pass

    def _on_shift_rpm_changed(self, rpm: int) -> None:
        """The driver set the upshift point for the selected discipline's sheet."""
        outcome = self._setups.set_shift_rpm(self._discipline, rpm)
        if not outcome.ok:
            self._garage_status(outcome.reason or "Could not set the shift beep.")
            return
        self._project_shift_rpm_to_config()
        self._garage_status(outcome.reason)
        self.refresh()

    def _on_shift_rpm_recommend(self) -> None:
        """Derive the upshift point from the car and write it to BOTH sheets.

        One recommendation yields both the qualifying and race points (race is a touch
        below for engine/fuel margin), so it fills each discipline's sheet at once.
        Nothing is fabricated: with no live rpm-alert and no car data the driver is told
        to drive the car first rather than given a guessed number.
        """
        from strategy.shift_rpm_recommendation import recommend_shift_rpm
        rec = recommend_shift_rpm(
            rpm_alert_max=self._last_rpm_alert_max(), power_rpm=self._car_power_rpm())
        if rec.qualifying_rpm is None:
            self._garage_status(rec.rationale)
            return
        self._setups.set_shift_rpm("race", rec.race_rpm)
        self._setups.set_shift_rpm("qualifying", rec.qualifying_rpm)
        self._project_shift_rpm_to_config()
        self._garage_status(
            f"Shift beep set from the car — qualifying {rec.qualifying_rpm} RPM, "
            f"race {rec.race_rpm} RPM. {rec.rationale}")
        self.refresh()

    def _last_rpm_alert_max(self):
        """GT7's own per-car upshift indicator from the latest packet, if any."""
        for attr in ("_last_packet", "last_packet"):
            p = getattr(self._window, attr, None)
            if p is not None:
                v = getattr(p, "rpm_alert_max", None)
                if v:
                    return v
        return None

    def _car_power_rpm(self):
        """The car's peak-power RPM from its specs, if the window can supply them."""
        try:
            fn = getattr(self._window, "_load_car_specs_for_current", None)
            if callable(fn):
                _name, specs = fn()
                return (specs or {}).get("power_rpm")
        except Exception:
            pass
        return None

    def _on_apply(self, field_values: dict) -> None:
        """Write the shown recommendation onto the sheet (shown == applied).

        The exact {field: value} the driver saw goes to the service, which stores it and
        keeps the previous sheet so the change can be undone in one step.
        """
        outcome = self._setups.apply(self._discipline, field_values)
        self._garage_status(outcome.reason)
        if outcome.ok:
            self._mirror_to_classic(self._discipline)
        self.refresh()

    def _on_revert(self, node_id: str) -> None:
        """Load a lineage revision, or (no id) undo the last apply.

        The lineage's "Load this setup" passes a "rev{n}" node id — that loads a past
        revision's tune back onto the sheet so the driver can re-enter it in GT7. The
        Outcome page's revert passes no id — that is the one-step undo of the last change.
        """
        nid = str(node_id or "")
        if nid.startswith("rev"):
            try:
                revision = int(nid[3:])
            except (TypeError, ValueError):
                revision = 0
            outcome = self._setups.load_revision(self._discipline, revision)
        else:
            outcome = self._setups.revert(self._discipline)
        self._garage_status(outcome.reason)
        if outcome.ok:
            self._mirror_to_classic(self._discipline)
        self.refresh()

    def _garage_status(self, text: str) -> None:
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is not None and hasattr(gp, "set_status"):
                gp.set_status(text)
        except Exception:
            pass

    def _on_analyse(self) -> None:
        """Run the setup brain over the current sheet, off the Qt thread.

        The result comes back as an OBJECT, so every outcome is reported — including
        "finished with nothing to change", which the old text-box path could not tell
        apart from "still running".
        """
        discipline = self._discipline
        self._pending_work = "analyse"
        self._garage_status("Analysing the current setup…")
        self._spawn(lambda: self._analysis_done.emit(self._setups.analyse(
            discipline, live_corner_aggregates=self._live_corner_aggregates())))

    def _live_corner_aggregates(self) -> list:
        """Live per-corner telemetry, when the host runs an aggregator ([] otherwise)."""
        try:
            tel = getattr(self._window, "_live_corner_tel", None)
            return list(tel.aggregates()) if tel is not None else []
        except Exception:
            return []

    def _on_analysis_done(self, result) -> None:
        """Report what the analysis concluded — every outcome, never silence."""
        self._pending_work = ""
        self._last_analysis = result
        self._garage_status(result.headline)
        self.refresh()

    def _on_build_baseline(self, discipline: str = "") -> None:
        """Author the initial setup for BOTH sheets through the headless engine."""
        self._pending_work = "baseline"
        self._garage_status(
            "Building the initial setup for the Race and Qualifying sheets…")
        self._spawn(lambda: self._baseline_done.emit(
            self._setups.build_initial_setup()))

    def _on_baseline_done(self, result) -> None:
        """Confirm each sheet individually — a sheet that did not build is never
        implied to have built."""
        self._pending_work = ""
        self._garage_status(result.headline)
        for built in result.built:
            self._mirror_to_classic(built)
        self.refresh()

    # ---- event selection / creation --------------------------------------
    def _on_activate_event(self, event_name: str) -> None:
        """Switch the event being prepared, through the headless service.

        Previously this drove the classic Event Planner's QListWidget and called its
        activation handler. It now saves + activates directly, so switching events does
        not depend on the old UI existing.
        """
        name = str(event_name or "").strip()
        if not name:
            return
        try:
            result = self._events.save_and_activate(self._events.draft_for(name))
        except Exception:
            result = None
        if result is not None and not result.ok:
            self._guidance_status(result.message or "Could not switch to that event.")
        self._review_cache.clear()
        self._last_guidance_view = None
        self.refresh()

    def _on_manage_events(self) -> None:
        """Open the NATIVE event setup, primed with the events already known.

        This used to raise the classic Event Planner window. Creating an event is part
        of the guided flow, not a trip into the old UI.
        """
        page = getattr(self._shell, "event_setup_page", None)
        if page is None:
            return
        try:
            page.set_existing_events([str(e.get("name") or "")
                                      for e in self._events.known_events()
                                      if str(e.get("name") or "").strip()])
            page.set_draft(self._events.draft_for(""))
        except Exception:
            pass
        self._navigate("event_setup")

    def _on_event_draft_open(self, event_name: str) -> None:
        """Load an existing event into the flow for editing/continuing."""
        page = getattr(self._shell, "event_setup_page", None)
        if page is None:
            return
        try:
            page.set_draft(self._events.draft_for(event_name))
        except Exception:
            pass

    def _on_event_draft_saved(self, draft) -> None:
        """Save + activate through the headless service, then go back to Home."""
        page = getattr(self._shell, "event_setup_page", None)
        try:
            result = self._events.save_and_activate(draft)
        except Exception as exc:
            if page is not None:
                from services.event_setup import DraftIssue
                page.show_issues([DraftIssue("", f"Could not save the event: {exc}")])
            return
        if not result.ok:
            if page is not None:
                page.show_issues(result.issues or ())
            return
        # The active event changed — every surface must be rebuilt against it.
        self._review_cache.clear()
        self._last_guidance_view = None
        self.refresh()
        self._navigate("home")

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
        """Persist the feedback, then BUILD the outcome it is half of.

        Submitting feedback used to navigate to an empty Outcome screen: nothing ever
        reconciled the driver's answers against what the run measured, so the page had
        nothing to show. The outcome is now built from the recorded laps plus the
        feedback, compared against the previous recorded run.
        """
        try:
            window = self._window
            for name in ("record_driver_feedback", "_record_driver_feedback", "save_driver_feedback"):
                fn = getattr(window, name, None)
                if callable(fn):
                    fn(dict(feedback or {}))
                    break
        except Exception:
            pass
        self._feed_outcome(feedback)
        self.refresh()

    def _feed_outcome(self, feedback=None) -> None:
        """Reconcile the reviewed run with the driver's feedback onto the Outcome page."""
        try:
            page = getattr(self._shell, "practice_outcome", None)
            if page is None:
                return
            from strategy.practice_run_review import build_run_outcome
            from ui.components.practice_outcome import PracticeOutcomeVM
            _last, prev_id = self._recorded_pair()
            review = self._review_for(self._review_session_id())
            previous = self._review_for(prev_id)
            outcome = build_run_outcome(review, feedback=feedback, previous=previous)
            page.set_outcome(PracticeOutcomeVM(
                verdict=outcome.verdict, verdict_summary=outcome.summary,
                telemetry_findings=outcome.telemetry_findings,
                feedback_summary=outcome.feedback_summary,
                agreements=outcome.agreements, contradictions=outcome.contradictions,
                changed_vs_previous=outcome.changed_vs_previous,
                confidence=outcome.confidence,
                primary_action_label=outcome.primary_action_label,
                primary_action_key=outcome.primary_action_key,
                secondary_action_label=outcome.secondary_action_label,
                secondary_action_key=outcome.secondary_action_key))
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
                self._gather_more_data()
            else:
                self._navigate("garage")
        except Exception:
            pass

    def _gather_more_data(self) -> None:
        """"Gather more data" = do ANOTHER run of the same kind, now.

        This used to navigate to Practice — the page the driver was already standing on
        — so the button appeared to do nothing. The verdict was inconclusive because the
        run needs repeating, so the action opens that repeat run and puts the driver on
        the run card with it already recording.
        """
        run_type = self._recorded_run_domain()
        from strategy.run_brief import brief_for_run_type
        brief = brief_for_run_type(run_type)
        # An open run already covers this; don't try to start a second one.
        if self._runs.open_run() is not None:
            self._show_run_card()
            self._run_status("A run is already open — drive it, then press “End run & record”.")
            return
        plan = self._runs.start_run(objective_domain=brief.domain,
                                    objective_headline=brief.objective)
        self._show_run_card()
        if not plan.ok:
            self._run_status(plan.reason or "Could not start another run.")
            return
        self._run_status(
            f"Another {brief.run_name} is open — drive it the same way, then press "
            f"“End run & record”. Two matching runs is what turns one result into evidence.")
        self.refresh()

    def _show_run_card(self) -> None:
        """Put Practice on screen with the Run card tab selected."""
        self._navigate("practice")
        try:
            shell = self._shell
            btn = getattr(shell, "_btn_runcard", None)
            stack = getattr(shell, "_practice_stack", None)
            if btn is not None:
                btn.setChecked(True)
            if stack is not None:
                stack.setCurrentIndex(0)
        except Exception:
            pass

    def _on_build_plan(self) -> None:
        """Build the race plan from the runs recorded against this event."""
        self._plan_status("Building the race plan from your recorded runs…")
        self._spawn(lambda: self._plan_done.emit(self._plans.build_plan()))

    def _on_plan_done(self, plan) -> None:
        self._plan_status(plan.headline)
        self.refresh()

    def _plan_status(self, text: str) -> None:
        try:
            sp = getattr(self._shell, "strategy_page", None)
            if sp is not None and hasattr(sp, "set_status"):
                sp.set_status(text)
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
        """Host the real engineering panel INSIDE the new shell.

        This used to raise the classic dashboard window, throwing the driver back into
        the old UI to read evidence. The panel is instead borrowed from the (hidden)
        classic tab widget and re-parented into the Library, then handed back on Back —
        so the fully-wired, already-fed panel is reused without a second window and the
        classic tab set is left exactly as it was found.
        """
        lib = getattr(self._shell, "library_page", None)
        if lib is None:
            return
        key, title, note = _LIBRARY_TAB.get(
            str(area or ""), ("development_history", "Development History", ""))
        widget = self._borrow_classic_tab(key)
        lib.show_panel(widget, title=title, note=note if widget is None else "")

    def _borrow_classic_tab(self, key: str):
        """Detach a classic tab page so it can be hosted natively. None if absent."""
        try:
            window = self._window
            tabs = getattr(window, "_tabs", None)
            get_index = getattr(window, "get_tab_index", None)
            if tabs is None or not callable(get_index):
                return None
            idx = int(get_index(key))
            if idx < 0:
                return None
            widget = tabs.widget(idx)
            if widget is None:
                return None
            self._borrowed = (key, idx, tabs.tabText(idx), widget)
            tabs.removeTab(idx)
            return widget
        except Exception:
            return None

    def _return_classic_tab(self) -> None:
        """Put a borrowed classic tab page back where it came from."""
        borrowed = getattr(self, "_borrowed", None)
        if not borrowed:
            return
        _key, idx, label, widget = borrowed
        self._borrowed = None
        try:
            lib = getattr(self._shell, "library_page", None)
            if lib is not None and hasattr(lib, "release_panel"):
                lib.release_panel()
            tabs = getattr(self._window, "_tabs", None)
            if tabs is not None and widget is not None:
                tabs.insertTab(int(idx), widget, label)
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


def _active_setup(window, purpose: str = "Race"):
    """(label, applied) for the setup currently on the car. Never raises.

    ``ActiveSetupAuthority.active_setup`` takes (identity, purpose) and ``ActiveSetup``
    exposes ``label()`` and ``is_active_on_car`` — the previous no-argument call raised
    TypeError into a bare except, so the shell could never show an active setup and the
    header sat on "Setup: —" no matter what the driver applied.
    """
    try:
        auth = getattr(window, "_setup_authority", None)
        if auth is None or not hasattr(auth, "active_setup"):
            return "", False
        from data.setup_state_authority import SetupIdentity
        ev = window._build_event_context() if hasattr(window, "_build_event_context") else None
        ident = SetupIdentity(
            car=str(getattr(ev, "car", "") or ""),
            track=str(getattr(ev, "track", "") or ""),
            layout_id=str(getattr(ev, "layout_id", "") or ""),
        )
        active = auth.active_setup(ident, purpose)
        if active is None:
            return "", False
        label = active.label() if callable(getattr(active, "label", None)) else ""
        return str(label or getattr(active, "name", "") or ""), bool(active.is_active_on_car)
    except Exception:
        return "", False


def _track_choices():
    """(locations, layouts_by_location) for the track pickers. Never raises.

    ``layouts_by_location`` maps each location id to ONLY its own layouts, so choosing a
    circuit shows that circuit's layouts — not a flat list of every "Full Course" of
    every track. Uses the same view-model helpers the classic tab uses, so the lists
    read identically.
    """
    try:
        from data.track_intelligence import load_track_seed
        from ui.track_modelling_vm import (
            build_layout_display_items, build_location_display_items,
        )
        seed = load_track_seed()
        locations = [(loc_id, display)
                     for display, loc_id in build_location_display_items(seed)]
        layouts_by_location = {
            loc_id: [(lay_id, lay_display)
                     for lay_display, lay_id in build_layout_display_items(seed, loc_id)]
            for _display, loc_id in build_location_display_items(seed)
        }
        return locations, layouts_by_location
    except Exception:
        return (), {}
