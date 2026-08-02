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
    #: PTT strategy acknowledgement — emitted by the voice listener thread and
    #: dispatched on the Qt thread so the slot can safely call refresh().
    _voice_strategy_ack = pyqtSignal(str)

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
        #: The live session the driver has entered: None (plain practice, race-vs-qual
        #: taken from the selected discipline), "qualifying" (Begin Qualifying pressed),
        #: or "race" (a live race detected from telemetry). Drives the runtime shift-beep
        #: RPM mode and the announcer's session mode. See ``_push_practice_mode``.
        self._live_session_mode: Optional[str] = None
        #: The last live race phase reported by the telemetry bridge — "IN PIT",
        #: "RACING", "FINISHED" — used to surface the pit fuel call on the Live Pit Wall.
        self._live_race_phase: str = ""
        #: Driver override for track wetness (qualifying tyre rule). None = follow the
        #: event weather; True/False = the driver has said the track is wet/dry (the only
        #: signal for Random Weather or a track that changes, since GT7 reports no rain).
        self._track_wet: Optional[bool] = None
        #: The cycle the wet override belongs to; when the active cycle changes the
        #: override is dropped so a wet-toggle never leaks from one event to the next.
        self._wet_cycle_id: Optional[str] = None
        #: "" or a short description of the long-running Garage job in flight, so a
        #: pressed Analyse/Baseline button is never silent.
        self._pending_work = ""
        #: The write side of the guided practice loop. Without it, nothing the driver
        #: does in a run ever reaches the event programme, so the engineer never moves.
        from ui.practice_run_recorder import PracticeRunRecorder
        self._runs = PracticeRunRecorder(db=db, config=self._config)
        #: The authoritative live Practice recording coordinator (Live Activation 1). None
        #: until an explicit, fully-resolved Practice activation opens a canonical session run;
        #: while set it is the source of truth for the live valid-lap count + connected state.
        self._live_practice = None
        #: The Practice Engineer's message choreographer (§7). Edge-driven: it speaks the brief,
        #: recording confirmation, progress, invalid-lap feedback, sufficiency and conclusion once
        #: each, and stays silent between — anti-chatter is structural.
        from strategy.practice_engineer_choreography import PracticeEngineerVoice
        self._practice_voice = PracticeEngineerVoice()
        #: The live telemetry session the coordinator adopted, and the last activation block
        #: reason (surfaced when recording is blocked by unresolved context).
        self._live_practice_session_id = 0
        self._live_practice_block = ""
        #: The authoritative live Qualifying recording coordinator (Live Activation 2). None until
        #: an explicit, fully-resolved Qualifying activation opens a canonical run; while set it is
        #: the source of truth for the live qualifying phase + personal best. It reuses the SAME
        #: generic lifecycle as Practice, composed with the qualifying phase machine.
        self._live_qualifying = None
        self._live_qualifying_session_id = 0
        self._live_qualifying_block = ""
        #: Previous telemetry on-track flag, for detecting the qualifying pit-exit (out-lap) and
        #: box edges; and the phase the qualifying engineer last spoke, for phase-edge anti-chatter.
        self._qual_on_track_prev = None
        self._qual_spoken_phase = ""
        #: The overall out-lap tyre warm-up status last spoken (cold/building/ready/hot), so the
        #: engineer updates only on a genuine change as temps rise — not every tick.
        self._qual_tyre_status_prev = ""
        #: The authoritative live Race recording coordinator (Live Activation 3). None until an
        #: explicit, fully-resolved Race activation opens a canonical run against a coherent race
        #: plan; while set it is the source of truth for the live lap total, pit stops and race
        #: phase. It reuses the SAME generic lifecycle as Practice/Qualifying, composed with the
        #: race engineer phase machine.
        self._live_race = None
        self._live_race_session_id = 0
        self._live_race_block = ""
        #: Previous canonical race/pit phase signals (for detecting race-phase edges), and the race
        #: phase the race engineer last spoke, for phase-edge anti-chatter.
        self._race_prev_race_phase = None
        self._race_prev_pit_phase = None
        self._race_spoken_phase = ""
        #: A finalised race telemetry session must never silently re-open as a new authoritative run
        #: on the next refresh (the race activity may still be open + telemetry still live). This
        #: records the just-finalised session so the driving loop does not re-activate it.
        self._live_race_finalised_session_id = 0
        #: The last finalised race session's post-session integrity audit (Live Activation 3 §5.2).
        #: A session that fails the audit is quarantined — finalised as history but not promoted to
        #: trusted event evidence (learning), never deleted.
        self._last_race_integrity = None
        #: The last race PTT answer spoken, for the REPEAT command.
        self._last_race_ptt_answer = ""
        #: The active race-day certification report (None until the user starts one). Held here so
        #: the guided panel's manual results accumulate and the verdict recomputes each edit.
        self._race_cert_report = None
        self._wire_certification_panel()
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
        from services.shift_strategy_store import ShiftStrategyStore, default_shift_strategy_path
        # The real MainWindow stores its config path as ``_config_path`` (leading
        # underscore) and always sets it; the original lookup read ``config_path``
        # (no underscore), which the real window does NOT have, so every store below was
        # constructed path-less and silently persisted NOTHING — the Garage reopened to
        # defaults after every restart. Read the real attribute first, then the name test
        # fakes use. When neither is present the path stays empty and the stores are
        # in-memory only (which is exactly what tests without a config want — the store
        # helpers treat "" as "do not persist").
        _cfg_path = getattr(window, "_config_path", None)
        if _cfg_path is None:
            _cfg_path = getattr(window, "config_path", None)
        _cfg_path = str(_cfg_path or "")
        self._sheets = SetupSheetStore(default_store_path(_cfg_path))
        self._shift_store = ShiftStrategyStore(default_shift_strategy_path(_cfg_path))
        #: The profile the driver last selected in the Shift Strategy panel.
        #: Persisted in-memory; reset to "qualifying" on bridge restart.
        self._shift_profile = "qualifying"
        # Persisted applied-revision history: fills the Garage Lineage tab and lets a
        # past setup be loaded back ("the settings I'm running in GT7").
        self._setup_history = SetupHistoryStore(default_history_path(_cfg_path))
        # User car weight-distribution overlay: persists the driver's % front value per
        # car so it survives a restart. The resolver is told the overlay path once so
        # subsequent resolves merge it on top of the seed without any restart.
        from services.car_weight_dist_store import CarWeightDistStore, default_car_weight_dist_path
        import data.car_weight_distribution as _wdmod
        _overlay_path = default_car_weight_dist_path(_cfg_path)
        self._car_wt_store = CarWeightDistStore(_overlay_path)
        self._car_wt_mod = _wdmod
        _wdmod.set_overlay_path(_overlay_path)
        #: The driver's front weight distribution % entered in the Garage spinbox.
        #: Injected into SetupInputs whenever the baseline generator is invoked.
        #: None (or 0) = "use the drivetrain prior" (no physics override).
        self._front_weight_dist_pct: Optional[float] = None
        self._setups = SetupService(
            store=self._sheets, advisor=getattr(window, "_driving_advisor", None),
            authority=getattr(window, "_setup_authority", None), db=db,
            history=self._setup_history,
            inputs_provider=lambda: self._build_inputs())
        # Track modelling, headless and guided. Reuses the domain untouched; the
        # coordinator decides which actions are legal at each point.
        # Race plan, headless — the strategy page could previously only DISPLAY a plan
        # the classic tab had built, so in the new shell it stayed empty forever.
        from services.race_plan import RacePlanService
        self._plans = RacePlanService(db=db, config=self._config)
        self._plan_done.connect(self._on_plan_done)
        from services.track_modelling import TrackModellingService
        from services.track_modelling_pipeline import build_track_model_builders
        _tm_ctrl = getattr(window, "_tm_controller", None)
        self._tracks = TrackModellingService(
            capture_controller=_tm_ctrl,
            builders=build_track_model_builders(_tm_ctrl))
        #: Transient track-modelling status (e.g. why validation didn't pass). Re-applied
        #: every refresh so the 750ms tick doesn't wipe it; cleared by the next action.
        self._tm_status = ""
        #: After the track is approved we capture one out-lap through the pit lane and map
        #: it. ``_pit_lane_baseline_laps`` is the lap count at the moment mapping began, so
        #: the first NEW completed lap is the pit-lane lap we detect from.
        self._pit_lane_mode = False
        self._pit_lane_baseline_laps = 0
        #: Count of modelling laps already spoken, so each new lap is announced once.
        self._tm_last_spoken_lap = 0
        #: (loc, lay) -> on-disk station map, so the map draws for an already-modelled
        #: track without re-reading the large file every refresh.
        self._tm_disk_map_cache: dict = {}
        #: Scopes already seeded from the classic sheets — see ``_seed_sheets``.
        self._seeded: set = set()
        #: Scopes already seeded from applied history — see ``_seed_from_last_applied``.
        self._seeded_history: set = set()
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
        #: session_id -> discipline it was practised on, so Review tells race and
        #: qualifying runs apart (a review is otherwise blind to which setup was on).
        self._run_discipline: dict[int, str] = {}
        #: The active cycle's preparation report, resolved once per refresh (lock state).
        self._lock_report = None
        #: Track pickers are filled once — the circuit list does not change at runtime.
        self._track_choices_loaded = False
        #: The last StrategyReplanDecision dict from build_live_audio_strategy_view.
        self._live_decision = None
        #: True when the last decision recommends REPLAN_RECOMMENDED or REPLAN_URGENT,
        #: i.e. an PTT "accept plan" / "keep plan" command is actionable.
        self._live_pending = False
        #: The plan the driver accepted via PTT. Shown on the pit wall until a new
        #: event cycle clears it. Overrides the DB-persisted approved strategy only in
        #: the CURRENT session — the persisted row is never mutated here.
        self._live_accepted_plan = None
        #: Tyre compound override for the current test run. Set by the run-card compound
        #: selector; cleared when the run is recorded or discarded. The saved sheet is
        #: NEVER mutated — only the tracker call and this override change.
        self._test_compound_override: Optional[str] = None
        #: The compound codes last fed to the run-card selector. Only update the selector
        #: when the allowed-compound set changes — NOT on every 750ms tick — so the
        #: driver's pick isn't clobbered by the periodic refresh (FIX 1a).
        self._last_compound_codes: tuple = ()
        #: The strategy decision is recomputed ONCE PER LAP ("at the end of every lap"),
        #: not on every 750ms display tick — this is the driver's own model and it stops
        #: the replan warning flickering as live figures wobble mid-lap. The last audio
        #: view is cached and the lap it was computed for is remembered.
        self._live_audio_view = None
        self._live_decision_lap = None
        #: candidate_id of the last plan pushed to the RaceStrategyEngine via set_plan(),
        #: so the defensive _feed_live guard does not call set_plan() on every 750ms tick.
        self._last_engine_plan_key: str = ""

        self._timer = QTimer(self)
        self._timer.setInterval(max(200, int(refresh_ms)))
        self._timer.timeout.connect(self.refresh)

        self._wire_signals()
        self._wire_actions()
        self._voice_strategy_ack.connect(self._on_voice_strategy_ack)
        self._wire_voice()

    # ---- wiring -----------------------------------------------------------
    def _wire_signals(self) -> None:
        """Refresh when the app reports connection / lap / race-state changes.

        MainWindow stores the signal bridge as ``self._bridge`` (not ``self.bridge``);
        the original lookup used ``"bridge"`` so lap_completed was never connected and
        the shell did not update on each completed lap.
        """
        try:
            bridge = getattr(self._window, "_bridge", None)
            for sig_name in ("connection_changed", "lap_completed",
                             "car_detected", "strategy_status_changed"):
                sig = getattr(bridge, sig_name, None)
                if sig is not None:
                    sig.connect(lambda *_: self.refresh())
            # race_state_changed carries the phase text ("IN PIT" / "RACING" /
            # "FINISHED") — capture it so the Live Pit Wall can call the pit stop and
            # assert race mode, not just blindly refresh.
            rsc = getattr(bridge, "race_state_changed", None)
            if rsc is not None:
                rsc.connect(self._on_race_state)
        except Exception:
            pass

    def _on_race_state(self, phase: str) -> None:
        """Track the live race phase for the pit-wall display.

        We deliberately do NOT infer "we are racing" from telemetry here — a practice or
        qualifying session can look like RACING and the app would then apply the race
        setup/RPM/plan by mistake. Entering race mode is an EXPLICIT driver action (Start
        Race, see ``_on_start_race``). This only records the phase so the Live Pit Wall can
        show "IN PIT" and the pit fuel call, and releases race mode when the race is over.
        """
        p = str(phase or "").upper()
        self._live_race_phase = p
        if p == "FINISHED" and self._live_session_mode == "race":
            self._live_session_mode = None
        self.refresh()

    def dispatch(self, command) -> None:
        """Single typed-command entry point (Program 3 §10).

        A page or test issues a typed ``shell_commands.Command``; this routes it to
        the canonical operation. ADDITIVE — the existing widget→signal→bridge-slot
        wiring is unchanged, so this introduces the typed, auditable surface (and the
        seam where a command can later be context-stamped/validated) without churning
        the working handlers. A command whose underlying operation is not yet built,
        or does not map cleanly onto an existing handler, raises NotImplementedError
        naming the reason — it is NEVER silently swallowed nor forced onto a
        semantically-different handler."""
        from ui import shell_commands as _cmd
        if isinstance(command, _cmd.SelectEvent):
            self._on_activate_event(command.event_name or command.event_id)
        elif isinstance(command, _cmd.StartSessionRun):
            self._on_start_run()
        elif isinstance(command, _cmd.CompleteSessionRun):
            self._on_record_run()
        elif isinstance(command, _cmd.RecordDriverFeedback):
            self._on_feedback(dict(command.feedback or {}))
        elif isinstance(command, _cmd.ApplySetup):
            # ApplySetup(setup_snapshot_id) does not map onto _on_apply(field_values),
            # which applies AI field values, not a snapshot by id — routing it there
            # would be semantically wrong. Applying a snapshot by id lands in Phase E.
            raise NotImplementedError(
                "ApplySetup by snapshot id is delivered in Phase E (the existing "
                "apply path takes field values, not a snapshot id)")
        elif isinstance(command, (_cmd.SelectSession, _cmd.ResumeSessionRun,
                                  _cmd.StartTelemetryCapture, _cmd.CompleteLap,
                                  _cmd.ReportRaceIncident)):
            raise NotImplementedError(
                f"{type(command).__name__} is delivered in a later phase "
                f"(session orchestration / dynamic strategy)")
        elif isinstance(command, (_cmd.AcceptLearningProposal, _cmd.RejectLearningProposal)):
            raise NotImplementedError(
                f"{type(command).__name__} is delivered in Phase I (cross-event learning)")
        else:
            raise TypeError(f"unknown shell command: {command!r}")

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
                if hasattr(gp, "track_wet_changed"):
                    gp.track_wet_changed.connect(self._on_track_wet_toggled)
                if hasattr(gp, "shift_rpm_changed"):
                    gp.shift_rpm_changed.connect(self._on_shift_rpm_changed)
                if hasattr(gp, "shift_rpm_recommend_requested"):
                    gp.shift_rpm_recommend_requested.connect(self._on_shift_rpm_recommend)
                if hasattr(gp, "lock_requested"):
                    gp.lock_requested.connect(self._on_lock_setup)
                if hasattr(gp, "car_ranges_requested"):
                    gp.car_ranges_requested.connect(self._on_car_ranges)
                if hasattr(gp, "gearing_changed"):
                    gp.gearing_changed.connect(self._on_gearing_changed)
                if hasattr(gp, "ballast_changed"):
                    gp.ballast_changed.connect(self._on_ballast_changed)
                if hasattr(gp, "regulation_changed"):
                    gp.regulation_changed.connect(self._on_regulation_changed)
                if hasattr(gp, "front_weight_dist_changed"):
                    gp.front_weight_dist_changed.connect(self._on_front_weight_dist_changed)
                if hasattr(gp, "save_front_weight_dist_requested"):
                    gp.save_front_weight_dist_requested.connect(self._on_save_front_weight_dist)
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
        # IMPORTANT: _c must be defined BEFORE the shift-strategy sv block so that
        # the go_to_tab → _on_shift_go_to_tab connection actually fires (the original
        # ordering left _c undefined in that scope, silently swallowing all sv wires).
        shell = self._shell
        _c = self._safe_connect
        # Shift strategy signals — the view lives on garage_page.shift_strategy_view.
        try:
            sv = getattr(
                getattr(self._shell, "garage_page", None),
                "shift_strategy_view", None)
            if sv is not None:
                _c(sv, "profile_changed",       self._on_shift_profile_changed)
                _c(sv, "engine_data_seeded",    self._on_shift_engine_seeded)
                _c(sv, "recalculate_requested", self._on_shift_recalculate)
                _c(sv, "go_to_tab",             self._on_shift_go_to_tab)
                _c(sv, "calibrate_requested",   self._on_shift_calibrate_requested)
        except Exception:
            pass
        rc = getattr(shell, "run_card", None)
        _c(rc, "start_requested", self._on_start_run)
        _c(rc, "record_requested", self._on_record_run)
        _c(rc, "discard_requested", self._on_discard_run)
        _c(rc, "compound_change_requested", self._on_test_compound_change)
        _c(getattr(shell, "garage_page", None), "applied_in_game_confirmed",
           self._on_applied_in_game)
        _c(getattr(shell, "feedback_form", None), "submitted", self._on_feedback)
        _c(getattr(shell, "practice_outcome", None), "action_requested", self._on_outcome_action)
        _c(getattr(shell, "qualifying_page", None), "begin_requested",
           self._on_begin_qualifying)
        _c(getattr(shell, "strategy_page", None), "approve_requested", self._on_approve_strategy)
        _c(getattr(shell, "strategy_page", None), "build_requested", self._on_build_plan)
        _c(getattr(shell, "strategy_page", None), "plan_selected", self._on_select_plan)
        _c(getattr(shell, "strategy_page", None), "start_race_requested", self._on_start_race)
        _c(getattr(shell, "debrief_page", None), "action_requested", self._on_debrief_action)
        _c(getattr(shell, "library_page", None), "open_requested", self._on_library_open)
        _c(getattr(shell, "library_page", None), "back_requested", self._return_classic_tab)
        tmp = getattr(shell, "track_model_page", None)
        _c(tmp, "track_selected", self._on_track_selected)
        _c(tmp, "action_requested", self._on_track_action)
        _c(tmp, "segment_action", self._on_track_segment)
        _c(tmp, "segment_rename", self._on_track_segment_rename)
        _c(getattr(shell, "programme_page", None), "start_next_requested",
           self._on_programme_start_next)
        _c(getattr(shell, "guidance", None), "read_aloud_requested", self._on_read_aloud)
        home = getattr(shell, "home_page", None)
        _c(home, "event_activate_requested", self._on_activate_event)
        _c(home, "manage_events_requested", self._on_manage_events)
        _c(home, "event_complete_requested", self._on_finish_event)
        esp = getattr(shell, "event_setup_page", None)
        _c(esp, "save_requested", self._on_event_draft_saved)
        _c(esp, "edit_requested", self._on_event_draft_open)

    def _wire_voice(self) -> None:
        """Register the strategy-ack callback with the PTT query listener.

        The query listener runs on its own thread; it calls the handler which emits the
        ``_voice_strategy_ack`` signal, delivering the action to the Qt thread where the
        slot can safely call refresh() and update widgets.
        """
        try:
            ql = getattr(self._window, "_query_listener", None)
            if ql is not None and hasattr(ql, "set_strategy_ack_handler"):
                ql.set_strategy_ack_handler(
                    lambda action: self._voice_strategy_ack.emit(str(action or "")))
        except Exception:
            pass

    def _active_session_run_id(self) -> str:
        """The canonical run_id of the session currently being recorded, or ''."""
        try:
            sid = self._live_session_id()
            if sid and self._db is not None and hasattr(self._db, "get_run_for_session"):
                return str((self._db.get_run_for_session(sid) or {}).get("run_id") or "")
        except Exception:
            pass
        return ""

    def _active_event_id(self) -> int:
        """The stable event_id of the active preparation cycle, or 0."""
        try:
            cfg = self._config if isinstance(self._config, dict) else {}
            cid = str(cfg.get("active_cycle_id") or "")
            if cid and self._db is not None and hasattr(self._db, "get_preparation_cycle"):
                return int((self._db.get_preparation_cycle(cid) or {}).get("event_id") or 0)
        except Exception:
            pass
        return 0

    def _record_ptt_interaction(self, *, resolved_action: str = "", recognised_action: str = "",
                                command_class: str = "", intent_confidence: float = 0.0,
                                ambiguous: bool = False, response: str = "",
                                fallback_state: str = "") -> None:
        """Best-effort persist of a PTT interaction with the active context (Phase F /
        §19), so a wrong response is traceable. The raw transcript is NEVER stored
        (push_to_talk invariant). Never raises."""
        db = getattr(self, "_db", None)
        if db is None or not hasattr(db, "record_ptt_interaction"):
            return
        try:
            import datetime as _dt
            from strategy.ptt_interaction import PttInteractionRecord
            cfg = self._config if isinstance(self._config, dict) else {}
            rec = PttInteractionRecord(
                event_id=self._active_event_id(),
                cycle_id=str(cfg.get("active_cycle_id") or ""),
                session_run_id=self._active_session_run_id(),
                lap_number=int(self._live_lap_count() or 0),
                session_type=str(self._live_session_mode or ""),
                recognised_action=str(recognised_action or resolved_action or ""),
                command_class=str(command_class or ""),
                intent_confidence=float(intent_confidence or 0.0),
                ambiguous=bool(ambiguous),
                resolved_action=str(resolved_action or ""),
                response=str(response or ""),
                fallback_state=str(fallback_state or ""),
                created_at=_dt.datetime.now().isoformat(timespec="seconds"),
            )
            db.record_ptt_interaction(rec.as_dict())
        except Exception:
            pass

    def _record_strategy_revision_on_accept(self, plan: dict) -> None:
        """Program 3 (Phase G / §16-17): an accepted replan is a material change, so
        snapshot the triggering race state and append a NEW IMMUTABLE strategy revision
        referencing it. Advisory only — this RECORDS the accepted plan (already shown via
        _live_accepted_plan); it executes nothing and mutates no live plan. Best-effort;
        never raises."""
        db = getattr(self, "_db", None)
        if db is None or not hasattr(db, "append_strategy_revision"):
            return
        try:
            import json as _json
            import datetime as _dt
            run_id = self._active_session_run_id()
            event_id = self._active_event_id()
            cfg = self._config if isinstance(self._config, dict) else {}
            cycle_id = str(cfg.get("active_cycle_id") or "")
            now = _dt.datetime.now().isoformat(timespec="seconds")
            snap_id = ""
            try:
                if hasattr(db, "append_race_state_snapshot"):
                    snap_id = db.append_race_state_snapshot(
                        session_run_id=run_id, event_id=event_id,
                        lap_number=int(self._live_lap_count() or 0), trigger="ptt_accept",
                        state_json=_json.dumps(self._live_decision or {})[:8000], created_at=now)
            except Exception:
                snap_id = ""
            db.append_strategy_revision(
                session_run_id=run_id, event_id=event_id, cycle_id=cycle_id,
                trigger="ptt_accept", plan_json=_json.dumps(plan or {}),
                reason="driver accepted the replan via PTT", confidence=0.0,
                race_state_snapshot_id=snap_id, communicated=True, created_at=now)
        except Exception:
            pass

    def _on_voice_strategy_ack(self, action: str) -> None:
        """Handle a PTT strategy acknowledgement on the Qt thread.

        "accept" — if a replan is pending and a best candidate exists, record the
        acknowledgement (advisory only, executes nothing) and store the candidate as the
        shown plan for this session.

        "keep" — record the acknowledgement and leave the shown plan unchanged.

        Any other action or nothing pending → safe no-op. Never raises.
        """
        try:
            from strategy.adaptive_live_strategy import acknowledge_strategy
            from ui.shell_feed_adapters import live_plan_dict_from_candidate
            # Program 3 (Phase F / §19): audit every strategy ack with its context —
            # including a no-op "accept with nothing pending" (a wrong-context signal).
            self._record_ptt_interaction(
                resolved_action=str(action or ""), command_class="strategy_ack",
                response=f"strategy ack: {action}")
            if action == "accept":
                if not self._live_pending:
                    return  # nothing to accept — safe no-op
                candidate = (self._live_decision or {}).get("best_candidate")
                if not candidate:
                    return
                ack = acknowledge_strategy(record_preference=True)
                # The domain contract: executes_anything is ALWAYS False.
                # This is asserted in tests; here we trust the domain.
                _ = ack.executes_anything   # noqa — referenced for documentation only
                plan = live_plan_dict_from_candidate(candidate)
                if plan:
                    self._live_accepted_plan = plan
                    self._record_strategy_revision_on_accept(plan)
                # Ensure the engine has the approved plan's stints so PTT can answer
                # "when do I pit" — the replan candidate is advisory-only and carries
                # no Stint-compatible data, so we reinforce the approved plan stints.
                self._push_plan_to_engine(self._approved_strategy())
                self.refresh()
            elif action == "keep":
                acknowledge_strategy(record_preference=False)
                # leave _live_accepted_plan unchanged
        except Exception:
            pass

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
        self._lock_report = None
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
        # Keep the live runtime's practice mode in step with the selected discipline, so
        # the shift beep uses the right (qualifying vs race) RPM for the session.
        self._push_practice_mode(self._discipline)
        # Drive the authoritative Practice coordinator from live telemetry BEFORE the surfaces
        # render, so the recording label, diagnostics header and engineer voice all read the
        # freshly-reconciled state this tick.
        self._drive_live_practice()
        self._drive_live_qualifying()
        self._drive_live_race()
        self._feed_garage()
        self._feed_shift_strategy()
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
                # When an AUTHORITATIVE live Practice run owns the recording (Live Activation
                # 1), its coordinator is the source of truth for the live valid-lap count and
                # the connected state; otherwise fall back to the session-derived count.
                laps_done, connected = self._authoritative_recording_progress()
                from strategy.run_brief import lap_progress_note
                rc.set_recording(str(run.get("title") or "Practice run"),
                                 laps_done, connected=connected,
                                 lap_note=lap_progress_note(card.target_laps, laps_done),
                                 push=card.push_level)
            else:
                rc.set_recording("")
        except Exception:
            pass
        # Practice Engineer choreography (§7): speak the brief / confirmation / progress /
        # invalid-lap / sufficiency / conclusion on their edges. Silent between edges.
        self._speak_practice_engineer()
        self._feed_run_review()
        # Compound selector on the run card — separate try block so a failure here does
        # not blank the run card itself.
        try:
            rc = getattr(self._shell, "run_card", None)
            if rc is not None:
                self._feed_run_compound_options(rc)
        except Exception:
            pass

    def _feed_run_review(self) -> None:
        """Show the laps of the run being reviewed — measured truth, not memory."""
        try:
            panel = getattr(self._shell, "run_laps", None)
            if panel is None:
                return
            panel.set_review(self._review_for(self._review_session_id()))
            from strategy.run_brief import brief_for_run_type
            run_type = self._recorded_run_domain()
            sid = int(self._review_session_id() or 0)
            disc = self._run_discipline.get(sid, "")
            disc_label = ("Qualifying setup" if disc == "qualifying"
                          else "Race setup" if disc == "race" else "")
            if run_type:
                brief = brief_for_run_type(run_type)
                panel.set_run_kind(brief.run_name, brief.reports, on=disc_label)
            else:
                panel.set_run_kind("", on=disc_label)
            # A coaching run's review is about the DRIVER — surface the coaching read so
            # it is not indistinguishable from a normal practice run.
            if hasattr(panel, "set_coaching"):
                if str(run_type).lower() == "coaching_run":
                    from strategy.practice_run_review import build_coaching_review
                    panel.set_coaching(build_coaching_review(
                        self._review_for(self._review_session_id())))
                else:
                    panel.set_coaching(None)
        except Exception:
            pass

    def _review_session_id(self):
        """The session the Review tab is about: the live one, else the last recorded run,
        else the most-recent recorded session for the active event.

        The final fallback keeps a practice run's laps reviewable even when the run was
        never bound to a preparation cycle (UAT: 'no laps persisting after a practice
        session'). It is event-scoped, so it never surfaces another event's session."""
        sid = self._live_session_id()
        if sid:
            return sid
        last, _prev = self._recorded_pair()
        if last:
            return last
        try:
            ev = self._window._build_event_context() if self._window else None
            eid = int(getattr(ev, "event_id", 0) or 0)
            if eid and self._db is not None and hasattr(self._db, "get_latest_session_for_event"):
                return int(self._db.get_latest_session_for_event(eid) or 0) or last
        except Exception:
            pass
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
        # Count distinct completed (timed) laps — the SAME measure the Practice
        # Review uses — rather than the raw total_laps counter (which also counts
        # out-/pit-/invalid rows), so the pit wall and Review can't disagree.
        try:
            return int(self._db.count_valid_laps(self._live_session_id())) if self._db else 0
        except Exception:
            return 0

    def _authoritative_recording_progress(self) -> "tuple":
        """(valid_lap_count, connected) from the authoritative live Practice coordinator when
        one owns the recording (Live Activation 1); otherwise the session-derived count + the
        telemetry connection. Never raises."""
        lp = getattr(self, "_live_practice", None)
        if lp is not None:
            try:
                from strategy.live_practice_activation import LiveRunState
                if lp.state in (LiveRunState.RECORDING, LiveRunState.PAUSED,
                                LiveRunState.DISCONNECTED):
                    return int(lp.valid_lap_count), bool(lp.is_recording)
            except Exception:
                pass
        return self._live_lap_count(), self._connected()

    def live_practice_diagnostics(self) -> dict:
        """Authoritative live-Practice identity + recording state for the diagnostics header
        (Live Activation 1 §9). Safe when no authoritative run is active. Never raises."""
        lp = getattr(self, "_live_practice", None)
        if lp is None:
            return {"active": False, "recording_state": "not_started"}
        try:
            idn = dict(getattr(lp, "identity", {}) or {})
            laps, connected = self._authoritative_recording_progress()
            state = getattr(lp, "state", None)
            return {
                "active": True,
                "recording_state": state.value if state is not None else "",
                "session_run_id": getattr(lp, "run_id", ""),
                "stint_id": getattr(lp, "stint_id", ""),
                "valid_lap_count": laps,
                "connected": connected,
                "session_type": idn.get("session_type", ""),
                "event_id": idn.get("event_id", ""),
                "event_programme_id": idn.get("event_programme_id", ""),
                "session_plan_id": idn.get("session_plan_id", ""),
                "car_id": idn.get("car_id", ""),
                "car_spec_revision_id": idn.get("car_spec_revision_id", ""),
                "setup_snapshot_id": idn.get("setup_snapshot_id", ""),
                "context_revision_id": idn.get("context_revision_id", ""),
                "driver_profile_version_id": idn.get("driver_profile_version_id", ""),
                "track_model_version_id": idn.get("track_model_version_id", ""),
            }
        except Exception:
            return {"active": False, "recording_state": "not_started"}

    def _practice_engineer_phase(self):
        """Build the engineer's phase snapshot from the authoritative coordinator + the current
        objective's brief (§7). Returns an empty phase when no run is active."""
        from strategy.practice_engineer_choreography import EngineerPhase
        lp = getattr(self, "_live_practice", None)
        if lp is None:
            return EngineerPhase()
        try:
            view = self._last_guidance_view if isinstance(self._last_guidance_view, dict) else {}
            headline = str((view.get("next_action") or {}).get("headline") or "")
            from strategy.practice_run_recording import domain_from_objective_headline
            from strategy.run_brief import brief_for_domain, _target_lap_bounds
            domain = domain_from_objective_headline(headline)
            brief = brief_for_domain(domain) if domain else None
            target_laps = brief.target_laps if brief is not None else ""
            lo, _hi = _target_lap_bounds(target_laps) if target_laps else (0, 0)
            return EngineerPhase(
                run_state=lp.state.value, valid_laps=int(lp.valid_lap_count),
                invalid_laps=int(lp.invalid_lap_count), invalid_reason=lp.last_invalid_reason,
                target_min=int(lo or 0), target_laps=target_laps,
                objective=domain or headline)
        except Exception:
            return EngineerPhase(run_state=getattr(getattr(lp, "state", None), "value", "not_started"))

    def _speak_practice_engineer(self) -> "object":
        """Observe the current phase and speak the engineer's message if the choreographer emits
        one on this edge (§7). Anti-chatter is inherited — no edge, no speech. Returns the message
        (or None) so callers/tests can inspect it. Never raises."""
        try:
            voice = getattr(self, "_practice_voice", None)
            if voice is None:
                return None
            msg = voice.observe(self._practice_engineer_phase())
            if msg is None or not msg.text:
                return msg
            announcer = getattr(self._window, "_announcer", None)
            if announcer is not None and hasattr(announcer, "announce"):
                from voice.announcer import Priority
                pri = {"high": Priority.HIGH, "medium": Priority.MEDIUM,
                       "low": Priority.LOW}.get(msg.priority.value, Priority.MEDIUM)
                announcer.announce(msg.text, pri, "practice_engineer")
            return msg
        except Exception:
            return None

    # ---- telemetry → coordinator driving (Live Activation 1) -------------- #
    #: Preparation-activity types that are driven as a live PRACTICE session (everything the
    #: event programme plans except a qualifying simulation, which is out of scope this phase).
    _PRACTICE_ACTIVITY_TYPES = frozenset({
        "baseline_practice", "setup_experiment", "coaching_run", "tyre_test", "fuel_test",
        "free_practice", "long_race_run", "strategy_validation_run", "final_setup_confirmation",
    })

    def _live_practice_context(self, live_session_id) -> dict:
        """Resolve the full canonical context for the current live Practice recording, ADOPTING
        the open telemetry session. The planned session type comes from the persisted activity —
        never from GT7. Missing required fields stay empty, so the gate blocks honestly."""
        ctx = {"live_session_id": int(live_session_id or 0)}
        try:
            run = self._runs.open_run() or {}
            atype = str(run.get("activity_type") or "").lower()
            ctx["planned_session_type"] = "Practice" if atype in self._PRACTICE_ACTIVITY_TYPES else ""
            ctx["session_plan_id"] = str(run.get("activity_id") or "")
            cid = self._runs.active_cycle_id()
            ctx["event_programme_id"] = cid
            cyc = self._db.get_preparation_cycle(cid) if (self._db and cid) else None
            event_id = int((cyc or {}).get("event_id") or 0)
            ctx["event_id"] = str(event_id or "")
            car_id = 0
            try:
                if hasattr(self._window, "_current_car_id"):
                    car_id = int(self._window._current_car_id() or 0)
            except Exception:
                car_id = 0
            ctx["car_id"] = str(car_id or "")
            try:
                specs = self._db.get_car_spec_revisions(car_id, event_id) or []
                ctx["car_spec_revision_id"] = str((specs[-1].get("spec_revision_id") if specs else "") or "")
            except Exception:
                ctx["car_spec_revision_id"] = ""
            try:
                dpv = self._db.get_current_driver_profile_version() or {}
                ctx["driver_profile_version_id"] = str(dpv.get("version_id") or "")
            except Exception:
                ctx["driver_profile_version_id"] = ""
            ecx = {}
            try:
                ecx = self._db.get_engineering_context_for_source("session", int(live_session_id)) or {}
                ctx["context_revision_id"] = str(ecx.get("fingerprint") or "")
            except Exception:
                ctx["context_revision_id"] = ""
            # Optional (where available): the approved track-model version for THIS session's
            # track/layout (reuse the engineering context we already resolved), and the setup
            # currently on the car for the practised discipline.
            try:
                tloc = str(ecx.get("track_location_id") or "")
                lay = str(ecx.get("layout_id") or "")
                tmv = self._db.get_approved_track_model_version(tloc, lay)
                ctx["track_model_version_id"] = str((tmv or {}).get("version_id") or "")
            except Exception:
                ctx["track_model_version_id"] = ""
            try:
                ctx["setup_snapshot_id"] = str(
                    self._setups.applied_setup_snapshot_id(self._discipline) or "")
            except Exception:
                ctx["setup_snapshot_id"] = ""
        except Exception:
            pass
        return ctx

    def _start_live_practice(self, live_session_id):
        """Activate an authoritative Practice run adopting the live telemetry session. On a
        blocked gate nothing is created and the exact reason is stored for the UI."""
        try:
            from strategy.live_practice_runtime import LivePracticeCoordinator
            from ui.live_practice_db_port import SessionDbLivePracticePort
            sid = int(live_session_id or 0)
            port = SessionDbLivePracticePort(self._db, lambda: self._live_practice_context(sid))
            co = LivePracticeCoordinator(port)
            act = co.activate()
            if not act.ok:
                self._live_practice = None
                self._live_practice_block = act.reason
                return act
            self._live_practice = co
            self._live_practice_session_id = sid
            self._live_practice_block = ""
            self._practice_voice.reset()
            co.telemetry_connected()
            return act
        except Exception:
            return None

    def _feed_new_laps_to_coordinator(self, live_session_id) -> None:
        """Feed DB laps the coordinator has not seen yet (lap_num > last_finalised) through the
        gate, so the authoritative valid-lap count + choreography track reality. Never raises."""
        try:
            lp = self._live_practice
            if lp is None or self._db is None:
                return
            laps = self._db.get_session_laps(int(live_session_id)) or []
            for row in sorted(laps, key=lambda r: int(r.get("lap_num") or 0)):
                ln = int(row.get("lap_num") or 0)
                if ln <= int(lp.last_finalised_lap):
                    continue
                lp.on_lap(session_run_id=lp.run_id, event_id=lp.event_id, lap_number=ln,
                          lap_time_ms=int(row.get("lap_time_ms") or 0),
                          is_out_lap=bool(row.get("is_out_lap")),
                          is_pit_lap=bool(row.get("is_pit_lap")), telemetry_complete=True)
        except Exception:
            pass

    def _drive_live_practice(self) -> None:
        """Reconcile the authoritative Practice coordinator with live telemetry each refresh.
        Additive + defensive: acts only while a practice activity + telemetry are present. The app
        decides the session (planned activity); telemetry only supplies connect + completed laps."""
        try:
            from strategy.live_practice_activation import LiveRunState
            lp = getattr(self, "_live_practice", None)
            connected = self._connected()
            live_sid = self._live_session_id()

            # (1) Activation — a practice activity is open, telemetry is live, context resolves.
            if lp is None or lp.state in (LiveRunState.COMPLETED, LiveRunState.ABANDONED):
                if connected and live_sid > 0 and self._runs.open_run() is not None:
                    self._start_live_practice(live_sid)
                return

            # Only reconcile a run WE started from telemetry (tracked adopted-session id). A
            # coordinator set directly (preview/test) is left untouched.
            if int(getattr(self, "_live_practice_session_id", 0)) <= 0:
                return

            # (2) Connection transitions.
            if not connected and lp.state == LiveRunState.RECORDING:
                lp.telemetry_lost()
            elif connected and lp.state == LiveRunState.STARTING:
                lp.telemetry_connected()
            elif connected and lp.state == LiveRunState.DISCONNECTED:
                if live_sid == int(getattr(self, "_live_practice_session_id", 0)):
                    lp.telemetry_connected()        # same telemetry session → resume the run
                # a DIFFERENT session cannot silently adopt this run — it stays disconnected
                # until the driver records or discards it (an explicit new run then activates).

            # (3) Feed any newly completed laps.
            if lp.state == LiveRunState.RECORDING:
                self._feed_new_laps_to_coordinator(int(getattr(self, "_live_practice_session_id", live_sid)))
        except Exception:
            pass

    # ---- telemetry → coordinator driving (Live Activation 2 — Qualifying) ---- #
    #: Preparation-activity types that are driven as a live QUALIFYING session. Symmetric with
    #: _PRACTICE_ACTIVITY_TYPES: the open run's activity decides the session, so the practice and
    #: qualifying coordinators are mutually exclusive (one open run has exactly one activity type).
    _QUALIFYING_ACTIVITY_TYPES = frozenset({"qualifying_simulation", "qualifying"})

    def _live_on_track(self):
        """Latest telemetry on-track flag (True on-track, False in pit/garage, None unknown).

        Read-only. The only telemetry signal the qualifying driving needs beyond completed laps:
        its False→True edge is the pit-exit (out-lap), its True→False edge is the box."""
        try:
            tracker = getattr(self._window, "_tracker", None)
            if tracker is not None and hasattr(tracker, "live_on_track"):
                return tracker.live_on_track
        except Exception:
            pass
        return None

    def _live_qualifying_context(self, live_session_id) -> dict:
        """Resolve the full canonical context for the current live Qualifying recording, ADOPTING
        the open telemetry session. The planned session type comes from the persisted qualifying
        activity — never from GT7. Missing required fields stay empty, so the gate blocks honestly.

        Identical resolution to ``_live_practice_context`` except the planned session type is
        ``Qualifying`` (for a qualifying activity), and the discipline read is qualifying."""
        ctx = {"live_session_id": int(live_session_id or 0)}
        try:
            run = self._runs.open_run() or {}
            atype = str(run.get("activity_type") or "").lower()
            ctx["planned_session_type"] = (
                "Qualifying" if atype in self._QUALIFYING_ACTIVITY_TYPES else "")
            ctx["session_plan_id"] = str(run.get("activity_id") or "")
            cid = self._runs.active_cycle_id()
            ctx["event_programme_id"] = cid
            cyc = self._db.get_preparation_cycle(cid) if (self._db and cid) else None
            event_id = int((cyc or {}).get("event_id") or 0)
            ctx["event_id"] = str(event_id or "")
            car_id = 0
            try:
                if hasattr(self._window, "_current_car_id"):
                    car_id = int(self._window._current_car_id() or 0)
            except Exception:
                car_id = 0
            ctx["car_id"] = str(car_id or "")
            try:
                specs = self._db.get_car_spec_revisions(car_id, event_id) or []
                ctx["car_spec_revision_id"] = str((specs[-1].get("spec_revision_id") if specs else "") or "")
            except Exception:
                ctx["car_spec_revision_id"] = ""
            try:
                dpv = self._db.get_current_driver_profile_version() or {}
                ctx["driver_profile_version_id"] = str(dpv.get("version_id") or "")
            except Exception:
                ctx["driver_profile_version_id"] = ""
            ecx = {}
            try:
                ecx = self._db.get_engineering_context_for_source("session", int(live_session_id)) or {}
                ctx["context_revision_id"] = str(ecx.get("fingerprint") or "")
            except Exception:
                ctx["context_revision_id"] = ""
            try:
                tloc = str(ecx.get("track_location_id") or "")
                lay = str(ecx.get("layout_id") or "")
                tmv = self._db.get_approved_track_model_version(tloc, lay)
                ctx["track_model_version_id"] = str((tmv or {}).get("version_id") or "")
            except Exception:
                ctx["track_model_version_id"] = ""
            try:
                # Qualifying always runs on the qualifying setup sheet.
                ctx["setup_snapshot_id"] = str(
                    self._setups.applied_setup_snapshot_id("qualifying") or "")
            except Exception:
                ctx["setup_snapshot_id"] = ""
        except Exception:
            pass
        return ctx

    def _start_live_qualifying(self, live_session_id):
        """Activate an authoritative Qualifying run adopting the live telemetry session. On a
        blocked gate nothing is created and the exact reason is stored for the UI."""
        try:
            from strategy.live_qualifying_runtime import LiveQualifyingCoordinator
            from ui.live_practice_db_port import SessionDbLivePracticePort
            sid = int(live_session_id or 0)
            port = SessionDbLivePracticePort(self._db, lambda: self._live_qualifying_context(sid))
            co = LiveQualifyingCoordinator(port)
            act = co.activate()
            if not act.ok:
                self._live_qualifying = None
                self._live_qualifying_block = act.reason
                return act
            self._live_qualifying = co
            self._live_qualifying_session_id = sid
            self._live_qualifying_block = ""
            self._qual_on_track_prev = None
            self._qual_spoken_phase = ""
            co.telemetry_connected()
            return act
        except Exception:
            return None

    def _feed_new_laps_to_qualifying_coordinator(self, live_session_id) -> None:
        """Feed DB laps the qualifying coordinator has not seen yet (lap_num > last_finalised)
        through the gate + phase machine, so the authoritative phase + personal best track
        reality. Never raises."""
        try:
            lq = self._live_qualifying
            if lq is None or self._db is None:
                return
            laps = self._db.get_session_laps(int(live_session_id)) or []
            for row in sorted(laps, key=lambda r: int(r.get("lap_num") or 0)):
                ln = int(row.get("lap_num") or 0)
                if ln <= int(lq.last_finalised_lap):
                    continue
                # Timing validity is the lap guard's verdict (out/pit/zero-time). GT7 track-limits
                # deletions are not captured per-lap in the DB yet, so a deleted flying lap can
                # only be sourced once that capture exists — the domain machine already handles it.
                lq.on_lap(session_run_id=lq.run_id, event_id=lq.event_id, lap_number=ln,
                          lap_time_ms=int(row.get("lap_time_ms") or 0),
                          is_out_lap=bool(row.get("is_out_lap")),
                          is_pit_lap=bool(row.get("is_pit_lap")), telemetry_complete=True)
        except Exception:
            pass

    def _drive_live_qualifying(self) -> None:
        """Reconcile the authoritative Qualifying coordinator with live telemetry each refresh.
        Additive + defensive: acts only while a qualifying activity + telemetry are present. The
        app decides the session (the planned qualifying activity); telemetry supplies the connect,
        the pit-exit/box edges (on-track flag) and the completed laps — never the session type."""
        try:
            from strategy.live_practice_activation import LiveRunState
            lq = getattr(self, "_live_qualifying", None)
            connected = self._connected()
            live_sid = self._live_session_id()

            # (1) Activation — a qualifying activity is open, telemetry is live, context resolves.
            if lq is None or lq.state in (LiveRunState.COMPLETED, LiveRunState.ABANDONED):
                run = self._runs.open_run()
                atype = str((run or {}).get("activity_type") or "").lower()
                if (connected and live_sid > 0 and run is not None
                        and atype in self._QUALIFYING_ACTIVITY_TYPES):
                    self._start_live_qualifying(live_sid)
                return

            # Only reconcile a run WE started from telemetry (tracked adopted-session id).
            if int(getattr(self, "_live_qualifying_session_id", 0)) <= 0:
                return

            # (2) Connection transitions (identical to Practice).
            if not connected and lq.state == LiveRunState.RECORDING:
                lq.telemetry_lost()
            elif connected and lq.state == LiveRunState.STARTING:
                lq.telemetry_connected()
            elif connected and lq.state == LiveRunState.DISCONNECTED:
                if live_sid == int(getattr(self, "_live_qualifying_session_id", 0)):
                    lq.telemetry_connected()

            # (3) Qualifying phase edges + newly completed laps, only while actively recording.
            if lq.state == LiveRunState.RECORDING:
                self._drive_qualifying_phase_edges(lq)
                self._feed_new_laps_to_qualifying_coordinator(
                    int(getattr(self, "_live_qualifying_session_id", live_sid)))
        except Exception:
            pass

    def _drive_qualifying_phase_edges(self, lq) -> None:
        """Translate the telemetry on-track flag into the qualifying phase machine's pit-exit and
        box events. False→True (left the pits) starts a new attempt's out-lap; True→False (back in
        the box) returns to preparation. Unknown (no telemetry) leaves the phase untouched."""
        try:
            cur = self._live_on_track()
            if cur is None:
                return
            prev = self._qual_on_track_prev
            if cur and prev is not True:
                # Went (or already) on track — begin the out-lap for this attempt. pit_exit only
                # advances while recording and (re)sets OUT_LAP, so a spurious repeat is harmless.
                lq.pit_exit()
            elif prev is True and not cur:
                lq.box()
            self._qual_on_track_prev = bool(cur)
        except Exception:
            pass

    def live_qualifying_diagnostics(self) -> dict:
        """Authoritative live-Qualifying identity + recording state for the diagnostics header
        (Live Activation 2). Session-type-aware: it carries the qualifying phase + personal best
        so the shared panel can render a qualifying-appropriate summary. Never raises."""
        lq = getattr(self, "_live_qualifying", None)
        if lq is None:
            return {"active": False, "recording_state": "not_started"}
        try:
            idn = dict(getattr(lq, "identity", {}) or {})
            state = getattr(lq, "state", None)
            best_ms = int(getattr(lq, "best_lap_ms", 0) or 0)
            return {
                "active": True,
                "recording_state": state.value if state is not None else "",
                "session_run_id": getattr(lq, "run_id", ""),
                "stint_id": getattr(lq, "stint_id", ""),
                "connected": bool(lq.is_recording),
                "session_type": idn.get("session_type", "qualifying") or "qualifying",
                "best_lap_ms": best_ms,
                "qualifying_phase": getattr(lq, "phase", ""),
                "attempt": int(getattr(lq, "attempt", 0) or 0),
                # A qualifying summary tracks the best flying lap + phase, not a valid-lap count.
                "headline": self._qualifying_diag_headline(best_ms, getattr(lq, "phase", ""),
                                                           int(getattr(lq, "attempt", 0) or 0)),
                "event_id": idn.get("event_id", ""),
                "event_programme_id": idn.get("event_programme_id", ""),
                "session_plan_id": idn.get("session_plan_id", ""),
                "car_id": idn.get("car_id", ""),
                "car_spec_revision_id": idn.get("car_spec_revision_id", ""),
                "setup_snapshot_id": idn.get("setup_snapshot_id", ""),
                "context_revision_id": idn.get("context_revision_id", ""),
                "driver_profile_version_id": idn.get("driver_profile_version_id", ""),
                "track_model_version_id": idn.get("track_model_version_id", ""),
            }
        except Exception:
            return {"active": False, "recording_state": "not_started"}

    @staticmethod
    def _qualifying_diag_headline(best_ms: int, phase: str, attempt: int) -> str:
        """Driver-facing one-line qualifying summary: best flying lap + current phase."""
        best = f"{best_ms / 1000.0:.3f}" if best_ms and best_ms > 0 else "—"
        ph = str(phase or "").replace("_", " ")
        head = f"Best {best}"
        if ph:
            head += f" · {ph}"
        if attempt:
            head += f" · attempt {attempt}"
        return head

    # ---- telemetry → coordinator driving (Live Activation 3 — Race) ---------- #
    #: The official (climax) RACE activity. Symmetric with the practice/qualifying activity sets:
    #: the open run's activity type decides the session, so the three coordinators are mutually
    #: exclusive (one open run has exactly one activity type). The race-development activities
    #: (long_race_run / strategy_validation_run) stay PRACTICE recordings — they are practice, not
    #: the event race — so only the "race" activity drives an authoritative Race recording.
    _RACE_ACTIVITY_TYPES = frozenset({"race"})

    def _live_race_context(self, live_session_id) -> dict:
        """Resolve the full canonical context for the current live Race recording, ADOPTING the open
        telemetry session. The planned session type comes from the persisted RACE activity — never
        from GT7 (which auto-classifies any multi-car lobby as a race). Missing required fields stay
        empty so the gate blocks honestly, and the active race plan's identity is carried so the
        race-plan coherence guard can reject a plan built for another event/car/track."""
        ctx = {"live_session_id": int(live_session_id or 0)}
        try:
            run = self._runs.open_run() or {}
            atype = str(run.get("activity_type") or "").lower()
            ctx["planned_session_type"] = "Race" if atype in self._RACE_ACTIVITY_TYPES else ""
            ctx["session_plan_id"] = str(run.get("activity_id") or "")
            cid = self._runs.active_cycle_id()
            ctx["event_programme_id"] = cid
            cyc = self._db.get_preparation_cycle(cid) if (self._db and cid) else None
            event_id = int((cyc or {}).get("event_id") or 0)
            ctx["event_id"] = str(event_id or "")
            car_id = 0
            try:
                if hasattr(self._window, "_current_car_id"):
                    car_id = int(self._window._current_car_id() or 0)
            except Exception:
                car_id = 0
            ctx["car_id"] = str(car_id or "")
            try:
                specs = self._db.get_car_spec_revisions(car_id, event_id) or []
                ctx["car_spec_revision_id"] = str((specs[-1].get("spec_revision_id") if specs else "") or "")
            except Exception:
                ctx["car_spec_revision_id"] = ""
            try:
                dpv = self._db.get_current_driver_profile_version() or {}
                ctx["driver_profile_version_id"] = str(dpv.get("version_id") or "")
            except Exception:
                ctx["driver_profile_version_id"] = ""
            ecx = {}
            try:
                ecx = self._db.get_engineering_context_for_source("session", int(live_session_id)) or {}
                ctx["context_revision_id"] = str(ecx.get("fingerprint") or "")
            except Exception:
                ctx["context_revision_id"] = ""
            # Live identity axes the race-plan guard compares against.
            tloc = str(ecx.get("track_location_id") or "")
            lay = str(ecx.get("layout_id") or "")
            ctx["track_id"] = tloc
            ctx["layout_id"] = lay
            ctx["config_id"] = str(ecx.get("config_id") or "")
            try:
                tmv = self._db.get_approved_track_model_version(tloc, lay)
                ctx["track_model_version_id"] = str((tmv or {}).get("version_id") or "")
            except Exception:
                ctx["track_model_version_id"] = ""
            try:
                # Race always runs on the race setup sheet.
                ctx["setup_snapshot_id"] = str(self._setups.applied_setup_snapshot_id("race") or "")
            except Exception:
                ctx["setup_snapshot_id"] = ""
            # The active race plan + its own bound identity (for the coherence guard). A plan that
            # records no identity of its own is treated as unscoped — the guard cannot prove a
            # mismatch and does not block; a plan whose config/car/track disagrees is rejected.
            try:
                plan = self._approved_strategy() or {}
                ctx["race_plan_id"] = str(plan.get("candidate_id") or "")
                ctx["race_plan_revision_id"] = str(plan.get("revision_id") or plan.get("approved_at") or "")
                ctx["plan_event_id"] = str(plan.get("event_id") or "")
                ctx["plan_car_id"] = str(plan.get("car_id") or "")
                ctx["plan_track_id"] = str(plan.get("track_id") or plan.get("track_location_id") or "")
                ctx["plan_layout_id"] = str(plan.get("layout_id") or "")
                ctx["plan_config_id"] = str(plan.get("config_id") or "")
            except Exception:
                pass
        except Exception:
            pass
        return ctx

    def _start_live_race(self, live_session_id):
        """Activate an authoritative Race run adopting the live telemetry session. On a blocked gate
        (wrong session, incomplete context, or a mis-scoped race plan) nothing is created and the
        exact reason is stored for the UI."""
        try:
            from strategy.live_race_runtime import LiveRaceCoordinator
            from ui.live_practice_db_port import SessionDbLivePracticePort
            sid = int(live_session_id or 0)
            port = SessionDbLivePracticePort(self._db, lambda: self._live_race_context(sid))
            co = LiveRaceCoordinator(port)
            act = co.activate()
            if not act.ok:
                self._live_race = None
                self._live_race_block = act.reason
                return act
            self._live_race = co
            self._live_race_session_id = sid
            self._live_race_block = ""
            self._race_prev_race_phase = None
            self._race_prev_pit_phase = None
            self._race_spoken_phase = ""
            co.telemetry_connected()
            return act
        except Exception:
            return None

    def _feed_new_laps_to_race_coordinator(self, live_session_id) -> None:
        """Feed DB laps the race coordinator has not seen yet (lap_num > last_finalised) through the
        gate + race phase machine, so the authoritative lap/pit totals track reality. Never raises."""
        try:
            lr = self._live_race
            if lr is None or self._db is None:
                return
            laps = self._db.get_session_laps(int(live_session_id)) or []
            for row in sorted(laps, key=lambda r: int(r.get("lap_num") or 0)):
                ln = int(row.get("lap_num") or 0)
                if ln <= int(lr.last_finalised_lap):
                    continue
                lr.on_lap(session_run_id=lr.run_id, event_id=lr.event_id, lap_number=ln,
                          lap_time_ms=int(row.get("lap_time_ms") or 0),
                          is_out_lap=bool(row.get("is_out_lap")),
                          is_pit_lap=bool(row.get("is_pit_lap")), telemetry_complete=True)
        except Exception:
            pass

    def _drive_live_race(self) -> None:
        """Reconcile the authoritative Race coordinator with live telemetry each refresh. Additive +
        defensive: acts only while a RACE activity + telemetry are present. The app decides the
        session (the planned race activity); telemetry supplies the connect, the race/pit phase edges
        and the completed laps — never the session type."""
        try:
            from strategy.live_practice_activation import LiveRunState
            lr = getattr(self, "_live_race", None)
            connected = self._connected()
            live_sid = self._live_session_id()

            # (1) Activation — a race activity is open, telemetry is live, context resolves.
            if lr is None or lr.state in (LiveRunState.COMPLETED, LiveRunState.ABANDONED):
                run = self._runs.open_run()
                atype = str((run or {}).get("activity_type") or "").lower()
                # Never re-open a session we already finalised (recorded or quarantined) as a new run.
                if (connected and live_sid > 0 and run is not None
                        and atype in self._RACE_ACTIVITY_TYPES
                        and live_sid != int(getattr(self, "_live_race_finalised_session_id", 0))):
                    self._start_live_race(live_sid)
                return

            # Only reconcile a run WE started from telemetry (tracked adopted-session id).
            if int(getattr(self, "_live_race_session_id", 0)) <= 0:
                return

            # (2) Connection transitions (identical to Practice/Qualifying).
            if not connected and lr.state == LiveRunState.RECORDING:
                lr.telemetry_lost()
            elif connected and lr.state == LiveRunState.STARTING:
                lr.telemetry_connected()
            elif connected and lr.state == LiveRunState.DISCONNECTED:
                if live_sid == int(getattr(self, "_live_race_session_id", 0)):
                    lr.telemetry_connected()

            # (3) Race/pit phase edges + newly completed laps, only while actively recording.
            if lr.state == LiveRunState.RECORDING:
                self._drive_race_phase_edges(lr)
                self._feed_new_laps_to_race_coordinator(
                    int(getattr(self, "_live_race_session_id", live_sid)))
        except Exception:
            pass

    def _drive_race_phase_edges(self, lr) -> None:
        """Translate the canonical race-state signals (RacePhase + PitPhase from the tracker) into
        the race engineer machine's events. Edge-based: an unchanged signal yields no event, so the
        machine only advances on a genuine transition. Never raises."""
        try:
            from strategy.race_engineer_state_machine import events_from_race_signals
            tracker = getattr(self._window, "_tracker", None)
            if tracker is None:
                return
            rp = getattr(getattr(tracker, "phase", None), "value", None) or getattr(tracker, "phase", None)
            pit = None
            try:
                pit = getattr(getattr(tracker, "pit_phase", None), "value", None)
            except Exception:
                pit = None
            events = events_from_race_signals(
                self._race_prev_race_phase, rp,
                prev_pit_phase=self._race_prev_pit_phase, pit_phase=pit)
            for ev in events:
                lr.apply_race_event(ev)
            self._race_prev_race_phase = rp
            self._race_prev_pit_phase = pit
        except Exception:
            pass

    def live_race_diagnostics(self) -> dict:
        """Authoritative live-Race identity + recording state for the diagnostics header (Live
        Activation 3). Session-type-aware: it carries the race phase, completed laps, pit stops and
        running best lap so the shared panel renders a race-appropriate summary. Never raises."""
        lr = getattr(self, "_live_race", None)
        if lr is None:
            return {"active": False, "recording_state": "not_started"}
        try:
            idn = dict(getattr(lr, "identity", {}) or {})
            state = getattr(lr, "state", None)
            best_ms = int(getattr(lr, "best_lap_ms", 0) or 0)
            completed = int(getattr(lr, "completed_laps", 0) or 0)
            stops = int(getattr(lr, "pit_stops_completed", 0) or 0)
            return {
                "active": True,
                "recording_state": state.value if state is not None else "",
                "session_run_id": getattr(lr, "run_id", ""),
                "stint_id": getattr(lr, "stint_id", ""),
                "connected": bool(lr.is_recording),
                "session_type": idn.get("session_type", "race") or "race",
                "best_lap_ms": best_ms,
                "completed_laps": completed,
                "pit_stops_completed": stops,
                "race_phase": getattr(lr, "phase", ""),
                "headline": self._race_diag_headline(best_ms, getattr(lr, "phase", ""), completed, stops),
                "event_id": idn.get("event_id", ""),
                "event_programme_id": idn.get("event_programme_id", ""),
                "session_plan_id": idn.get("session_plan_id", ""),
                "car_id": idn.get("car_id", ""),
                "car_spec_revision_id": idn.get("car_spec_revision_id", ""),
                "setup_snapshot_id": idn.get("setup_snapshot_id", ""),
                "context_revision_id": idn.get("context_revision_id", ""),
                "driver_profile_version_id": idn.get("driver_profile_version_id", ""),
                "track_model_version_id": idn.get("track_model_version_id", ""),
                "race_plan_id": idn.get("race_plan_id", ""),
                "race_plan_revision_id": idn.get("race_plan_revision_id", ""),
            }
        except Exception:
            return {"active": False, "recording_state": "not_started"}

    @staticmethod
    def _race_diag_headline(best_ms: int, phase: str, completed: int, stops: int) -> str:
        """Driver-facing one-line race summary: lap total + phase + best lap + stops."""
        best = f"{best_ms / 1000.0:.3f}" if best_ms and best_ms > 0 else "—"
        ph = str(phase or "").replace("_", " ")
        head = f"Lap {completed}"
        if ph:
            head += f" · {ph}"
        head += f" · best {best}"
        if stops:
            head += f" · {stops} stop{'s' if stops != 1 else ''}"
        return head

    def _speak_race_engineer(self) -> "object":
        """Speak the race engineer's phase-appropriate cue on each phase EDGE (Live Activation 3 §6).
        Anti-chatter: the line is spoken once when the race phase changes (grid → lights-out → pit
        entry/exit → finish), silent between. On a settled-racing edge it may relay the deterministic
        strategy advisory verbatim (the machine authors no strategy of its own). Returns the line (or
        "") so tests can inspect it. Never raises."""
        try:
            lr = getattr(self, "_live_race", None)
            if lr is None or not lr.is_recording:
                return ""
            phase = str(lr.phase or "")
            if phase == getattr(self, "_race_spoken_phase", ""):
                return ""
            self._race_spoken_phase = phase
            # On the racing edge, relay the current deterministic strategy advisory if one is
            # pending (never fabricated — only what the replan pipeline already produced this lap).
            advisory = ""
            try:
                if phase == "racing" and getattr(self, "_live_pending", False):
                    decision = getattr(self, "_live_decision", {}) or {}
                    advisory = str(decision.get("driver_message") or "")
            except Exception:
                advisory = ""
            line = lr.cue(advisory=advisory)
            if not line:
                return ""
            announcer = getattr(self._window, "_announcer", None)
            if announcer is not None and hasattr(announcer, "announce"):
                from voice.announcer import Priority
                # Pit/finish cues are HIGH (safety/closure); mid-race presence is MEDIUM.
                pri = Priority.HIGH if phase in ("pit_entry", "in_pit", "finished") else Priority.MEDIUM
                announcer.announce(line, pri, "race_engineer")
            return line
        except Exception:
            return ""

    def _audit_race_session(self, lr, sid):
        """Run the post-session race integrity audit for the coordinator ``lr`` over session ``sid``.
        Read-only; returns a RaceSessionIntegrityReport (or None on failure). Never raises."""
        try:
            from strategy.live_race_integrity import audit_race_session
            run = None
            try:
                run = self._db.get_run_for_session(int(sid)) if self._db else None
            except Exception:
                run = None
            laps = []
            try:
                laps = self._db.get_session_laps(int(sid)) or [] if self._db else []
            except Exception:
                laps = []
            idn = dict(getattr(lr, "identity", {}) or {})
            expected = {
                "event_id": idn.get("event_id", ""), "car_id": idn.get("car_id", ""),
                "track_id": idn.get("track_id", ""), "layout_id": idn.get("track_model_version_id", "")
                or idn.get("layout_id", ""), "session_type": "race",
            }
            return audit_race_session(run=run or {}, laps=laps, expected=expected)
        except Exception:
            return None

    def _build_canonical_race_state(self):
        """Build the current canonical live race state from the tracker (same source as the pit
        wall), or None. Read-only; never raises. Sourcing plan attrs from the window mirrors
        _feed_live so the PTT answer reads exactly what the surface shows."""
        try:
            tracker = getattr(self._window, "_tracker", None)
            if tracker is None or getattr(tracker, "race_type", None) is None:
                return None
            from strategy.canonical_live_race_state import build_canonical_live_race_state
            return build_canonical_live_race_state(
                tracker,
                elapsed_s=getattr(self._window, "_live_race_elapsed_s", None),
                telemetry_fresh=self._connected(),
                fuel_per_lap_plan=getattr(self._window, "_live_fuel_plan", None),
                lap_time_plan_s=getattr(self._window, "_live_pace_plan_s", None),
                recent_fuel_burn_samples=getattr(self._window, "_live_fuel_samples", None),
                recent_clean_lap_times_s=getattr(self._window, "_live_clean_lap_times", None),
                pit_loss_s=getattr(self._window, "_live_pit_loss_s", None),
                driver_reports=getattr(self._window, "_live_driver_reports", None))
        except Exception:
            return None

    def answer_race_ptt(self, intent) -> str:
        """Answer ONE bounded race PTT intent from the current canonical race state (Live Activation
        3 §6.2). The answer is sourced from live state, never stale UI text; unknown evidence yields
        an honest "I don't have that", and an unsupported intent an honest refusal. Never raises."""
        try:
            from strategy.race_ptt_answers import answer_race_query
            state = self._build_canonical_race_state()
            # Carry the authoritative best lap from the race coordinator, if one is recording.
            lr = getattr(self, "_live_race", None)
            if state is not None and lr is not None:
                try:
                    best_ms = int(getattr(lr, "best_lap_ms", 0) or 0)
                    if best_ms > 0:
                        object.__setattr__(state, "best_lap_s", best_ms / 1000.0)
                except Exception:
                    pass
            text, _supported = answer_race_query(
                intent, state, last_answer=getattr(self, "_last_race_ptt_answer", ""))
            self._last_race_ptt_answer = text
            return text
        except Exception:
            return ""

    def race_session_integrity(self) -> dict:
        """The last race session's integrity audit as a plain dict, for the certification workflow
        and the diagnostics inspection area. Empty when no race run has been finalised. Never raises."""
        try:
            report = getattr(self, "_last_race_integrity", None)
            return report.as_payload() if report is not None else {}
        except Exception:
            return {}

    # ---- race-day certification workflow (Live Activation 3 §7) ------------- #
    def _certification_evidence(self) -> dict:
        """Auto-capture the auditable evidence header from live app state (§7.3). Every field is
        best-effort; unknown stays absent (never fabricated). No wall-clock — the caller stamps
        ``captured_at`` if it wants one."""
        ev: dict = {}
        try:
            from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
            ev["db_version"] = DB_VERSION
            ev["rule_engine_version"] = RULE_ENGINE_VERSION
        except Exception:
            pass
        try:
            from data.repo_identity import resolve_repo_commit, short_commit
            sha = resolve_repo_commit(".")
            if sha:
                ev["git_commit"] = short_commit(sha)
        except Exception:
            pass
        try:
            ev["app_version"] = str(getattr(self._window, "_app_version", "") or "") or None
        except Exception:
            pass
        # Race identity + counts, from the authoritative race coordinator when present, else the
        # currently resolved race context.
        try:
            lr = getattr(self, "_live_race", None)
            idn = dict(getattr(lr, "identity", {}) or {}) if lr is not None else \
                self._live_race_context(self._live_session_id())
            ev["event_id"] = idn.get("event_id") or None
            ev["car_id"] = idn.get("car_id") or None
            ev["track_id"] = idn.get("track_id") or None
            ev["layout_id"] = idn.get("layout_id") or None
            if lr is not None:
                ev["run_ids"] = getattr(lr, "run_id", "") or None
                ev["lap_counts"] = getattr(lr, "completed_laps", None)
                ev["pit_event_counts"] = getattr(lr, "pit_stops_completed", None)
        except Exception:
            pass
        try:
            integ = self.race_session_integrity()
            ev["integrity_result"] = integ.get("summary") if integ else None
        except Exception:
            pass
        return {k: v for k, v in ev.items() if v is not None}

    def build_race_certification(self, scenario: str = "controlled-race-event",
                                 *, captured_at: str = "") -> "object":
        """Build a race certification report pre-filled with the evidence header + the stages that
        CAN be verified automatically (environment/build, identity resolution, and the post-session
        integrity audit). Physical stages (telemetry, live Practice/Qualifying/Race, voice, PTT,
        restart) stay NOT_TESTED — only a MANUAL result the user records can pass them, so a
        Certified verdict is impossible until the hardware UAT is done. Never raises."""
        from strategy.race_certification import (
            EvidenceKind, StageState, new_report, record_stage,
        )
        ev = self._certification_evidence()
        if captured_at:
            ev["captured_at"] = str(captured_at)
        report = new_report(scenario, evidence=ev)
        stages = report.stages
        # environment/build: the app is running these checks — automated PASS.
        stages = record_stage(stages, "environment_build", state=StageState.PASS,
                              evidence=EvidenceKind.AUTOMATED,
                              detail="app running; DB + rule-engine versions captured")
        # identity: PASS if the full canonical race context resolved (all required ids present).
        try:
            ctx = self._live_race_context(self._live_session_id())
            from strategy.live_practice_activation import resolve_live_race_activation, \
                validate_race_plan_context
            act = resolve_live_race_activation(
                ctx, planned_session_type=ctx.get("planned_session_type") or ctx.get("session_type"))
            plan_ok = validate_race_plan_context(ctx).ok
            if act.ok and plan_ok:
                stages = record_stage(stages, "identity", state=StageState.PASS,
                                      evidence=EvidenceKind.AUTOMATED,
                                      detail="full canonical identity + coherent race plan resolved")
            else:
                reason = act.reason if not act.ok else validate_race_plan_context(ctx).reason
                stages = record_stage(stages, "identity", state=StageState.NOT_TESTED,
                                      evidence=EvidenceKind.AUTOMATED, detail=reason)
        except Exception:
            pass
        # integrity audit: credit from the last finalised race session's audit, if any.
        try:
            integ = self.race_session_integrity()
            if integ:
                st = StageState.PASS if integ.get("promotion_allowed") else StageState.FAIL
                stages = record_stage(stages, "integrity_audit", state=st,
                                      evidence=EvidenceKind.AUTOMATED, detail=integ.get("summary", ""))
        except Exception:
            pass
        return report.__class__(scenario=report.scenario, stages=stages, evidence=ev)

    def _race_cert_store(self):
        """The additive race-certification report store, rooted beside the app config."""
        from data.race_certification_store import RaceCertificationStore
        base = "."
        try:
            import os as _os
            import config_paths
            path = getattr(self._window, "_config_path", None) or getattr(
                self._window, "config_path", None) or config_paths.resolve_config_path()
            if path:
                base = _os.path.dirname(str(path)) or "."
        except Exception:
            base = "."
        return RaceCertificationStore(base)

    def save_race_certification(self, report_id: str, report) -> str:
        """Persist a certification report (JSON + Markdown) to the store. Returns the JSON path."""
        try:
            return self._race_cert_store().save(report_id, report)
        except Exception:
            return ""

    def _wire_certification_panel(self) -> None:
        """Connect the guided certification panel's intents to the bridge. Defensive — the panel
        only exists on the live page in the new shell. Never raises."""
        try:
            panel = getattr(getattr(self._shell, "live_page", None), "certification", None)
            if panel is None:
                return
            panel.refresh_requested.connect(self.start_race_certification)
            panel.stage_recorded.connect(self._on_cert_stage_recorded)
            panel.export_requested.connect(self._on_cert_export)
        except Exception:
            pass

    def start_race_certification(self) -> None:
        """(Re)build the certification report from current app state (auto stages + evidence) and
        show it in the guided panel. The user then records the physical results. Never raises."""
        try:
            self._race_cert_report = self.build_race_certification()
            self._feed_certification()
        except Exception:
            pass

    def _on_cert_stage_recorded(self, key: str, state: str, evidence: str) -> None:
        """Apply a user-recorded manual result to the held report and refresh the panel + verdict."""
        try:
            if self._race_cert_report is None:
                self._race_cert_report = self.build_race_certification()
            from strategy.race_certification import record_stage
            stages = record_stage(self._race_cert_report.stages, str(key),
                                  state=str(state), evidence=str(evidence or "manual"))
            self._race_cert_report = self._race_cert_report.__class__(
                scenario=self._race_cert_report.scenario, stages=stages,
                evidence=self._race_cert_report.evidence)
            self._feed_certification()
        except Exception:
            pass

    def _on_cert_export(self, fmt: str) -> None:
        """Export the held report (JSON + Markdown are always written together to the store)."""
        try:
            if self._race_cert_report is None:
                return
            ev = self._race_cert_report.evidence if isinstance(
                self._race_cert_report.evidence, dict) else {}
            rid = "race-cert-" + (str(ev.get("event_id") or "event")) + "-" + (
                str(ev.get("git_commit") or "build"))
            path = self.save_race_certification(rid, self._race_cert_report)
            self._run_status(f"Certification exported ({str(fmt)}): {path}" if path
                             else "Could not export the certification report.")
        except Exception:
            pass

    def _feed_certification(self) -> None:
        """Push the held certification report to the guided panel (hides it when none). Never raises."""
        try:
            lp = getattr(self._shell, "live_page", None)
            if lp is None or not hasattr(lp, "set_certification"):
                return
            lp.set_certification(
                self._race_cert_report.as_json_payload() if self._race_cert_report is not None else {})
        except Exception:
            pass

    def _clear_race_voice_queue(self) -> None:
        """At race finish, drop any still-queued low-value chatter so the closing line is not
        buried and the engineer falls silent once the race is done (Live Activation 3 §6.1).
        Best-effort across the known announcer/voice surfaces; never raises."""
        try:
            announcer = getattr(self._window, "_announcer", None)
            for name in ("clear", "clear_queue", "flush", "cancel_all", "on_session_end", "reset"):
                fn = getattr(announcer, name, None)
                if callable(fn):
                    fn()
                    break
        except Exception:
            pass

    def _speak_qualifying_engineer(self) -> "object":
        """Speak the qualifying engineer's phase-appropriate cue on each phase EDGE (§7 analogue).
        Anti-chatter: the line is spoken once when the phase changes, silent between. Returns the
        line (or "") so tests can inspect it. Never raises."""
        try:
            lq = getattr(self, "_live_qualifying", None)
            if lq is None or not lq.is_recording:
                return ""
            phase = str(lq.phase or "")
            if phase == getattr(self, "_qual_spoken_phase", ""):
                return ""
            self._qual_spoken_phase = phase
            # Recall the driver's practice reference on the prep/out-lap where it helps.
            _last_s, best_s = self._live_last_best_lap_s()
            practice_best_ms = int(best_s * 1000) if best_s else 0
            line = lq.cue(practice_best_ms=practice_best_ms)
            if not line:
                return ""
            announcer = getattr(self._window, "_announcer", None)
            if announcer is not None and hasattr(announcer, "announce"):
                from voice.announcer import Priority
                announcer.announce(line, Priority.MEDIUM, "qualifying_engineer")
            return line
        except Exception:
            return ""

    def _speak_qualifying_tyre_warmup(self) -> "object":
        """Give ongoing OUT-LAP tyre-temperature guidance so the driver brings the tyres into the
        optimal window before the flying lap. Reads the live per-corner tyre states from the tracker
        and speaks only when the overall warm-up status CHANGES (cold → building → up-to-temp / too
        hot), so it updates as the temps rise without chattering. Silent outside the out-lap and when
        no live qualifying run owns the voice. Returns the spoken line (or "") for tests. Never
        raises."""
        try:
            lq = getattr(self, "_live_qualifying", None)
            if lq is None or not lq.is_recording or str(lq.phase or "") != "out_lap":
                # Leaving the out-lap re-arms the warm-up, so the next attempt announces afresh.
                self._qual_tyre_status_prev = ""
                return ""
            tracker = getattr(self._window, "_tracker", None)
            states = getattr(tracker, "tyre_states", None) if tracker is not None else None
            from strategy.qualifying_state_machine import qualifying_tyre_warmup
            status, line = qualifying_tyre_warmup(states)
            if not status or status == getattr(self, "_qual_tyre_status_prev", ""):
                return ""
            self._qual_tyre_status_prev = status
            if not line:
                return ""
            announcer = getattr(self._window, "_announcer", None)
            if announcer is not None and hasattr(announcer, "announce"):
                from voice.announcer import Priority
                # "Up to temp — go" and "you're cooking them" are the actionable ones → HIGH.
                pri = Priority.HIGH if status in ("ready", "hot") else Priority.MEDIUM
                announcer.announce(line, pri, "qualifying_engineer")
            return line
        except Exception:
            return ""

    def _live_last_best_lap_s(self) -> "tuple":
        """(last_lap_s, best_lap_s) from the live lap logger, or (None, None)."""
        try:
            logger = getattr(self._window, "_logger", None)
            if logger is None:
                return None, None
            best_ms = logger.best_lap_ms() if hasattr(logger, "best_lap_ms") else -1
            recs = logger.records() if hasattr(logger, "records") else []
            last_ms = getattr(recs[-1], "lap_time_ms", -1) if recs else -1
            best_s = best_ms / 1000.0 if best_ms and best_ms > 0 else None
            last_s = last_ms / 1000.0 if last_ms and last_ms > 0 else None
            return last_s, best_s
        except Exception:
            return None, None

    def _maybe_speak_engineer(self, text: str) -> None:
        """Speak the session engineer line ONCE per new lap (not every 750ms tick), so
        the engineer's voice tracks the session without chattering. Never raises."""
        try:
            if not text:
                return
            lap = self._live_lap_count()
            if lap == getattr(self, "_live_engineer_spoken_lap", None):
                return
            self._live_engineer_spoken_lap = lap
            announcer = getattr(self._window, "_announcer", None)
            if announcer is None or not hasattr(announcer, "announce"):
                return
            from voice.announcer import Priority
            announcer.announce(text, Priority.MEDIUM, "live_engineer")
        except Exception:
            pass

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
        # Finalise the authoritative session run (COMPLETING → COMPLETED) so it becomes history
        # and can never silently re-activate. Best-effort; the activity binding below is separate.
        try:
            lp = getattr(self, "_live_practice", None)
            if lp is not None and int(getattr(self, "_live_practice_session_id", 0)) == int(sid or 0):
                lp.complete()
        except Exception:
            pass
        # Same finalisation for an authoritative live Qualifying run (Live Activation 2), so it
        # becomes history and can never silently re-activate.
        try:
            lq = getattr(self, "_live_qualifying", None)
            if lq is not None and int(getattr(self, "_live_qualifying_session_id", 0)) == int(sid or 0):
                lq.complete()
        except Exception:
            pass
        # Same finalisation for an authoritative live Race run (Live Activation 3): COMPLETING →
        # COMPLETED closes the run + reaches the terminal FINISHED phase (queued voice is cleared).
        # Then a post-session integrity audit gates promotion to trusted event evidence — a session
        # with a blocker (invalid/placeholder identity, wrong session type, duplicate/orphan laps,
        # contradictory car/track) is QUARANTINED: finalised as history but not promoted, never
        # deleted or rewritten, with the exact reason surfaced for review.
        try:
            lr = getattr(self, "_live_race", None)
            if lr is not None and int(getattr(self, "_live_race_session_id", 0)) == int(sid or 0):
                report = self._audit_race_session(lr, int(sid or 0))
                self._last_race_integrity = report
                lr.complete()
                self._live_race_finalised_session_id = int(sid or 0)
                self._clear_race_voice_queue()
                if report is not None and not report.promotion_allowed:
                    self._run_status("Race held for review — not promoted to event evidence. "
                                     + report.summary)
                    self._feed_run_review()
                    self.refresh()
                    return
        except Exception:
            pass
        decision = self._runs.record_run(sid)
        if not decision.ok:
            self._run_status(decision.reason or "Could not record the run.")
            return
        # Keep the recorded run reviewable after the live session moves on, and keep the
        # one before it so the next outcome has something to compare against.
        if self._last_recorded_session_id != int(decision.session_id or 0):
            self._previous_recorded_session_id = self._last_recorded_session_id
        self._last_recorded_session_id = int(decision.session_id or 0)
        # Remember which discipline the driver was practising, so a race run and a
        # qualifying run are told apart in Review rather than lumped together.
        self._run_discipline[int(decision.session_id or 0)] = self._discipline
        # Clear the tyre-test override — the run is now bound and its compound tag is
        # fixed; subsequent runs start fresh from the sheet compound.
        self._test_compound_override = None
        msg = (f"Run recorded — {decision.reason} "
               f"Open Review to see the laps, then submit your feedback.")
        if decision.warning:
            msg += f"  ⚠ {decision.warning}"
        self._run_status(msg)
        self._feed_run_review()
        self._feed_outcome()
        self.refresh()

    def _on_discard_run(self) -> None:
        # Clear the tyre-test override — the discarded run never reached the programme,
        # so the next run should start from the sheet compound again.
        self._test_compound_override = None
        ok = self._runs.discard_run()
        self._run_status("Run discarded — nothing was recorded against the event."
                         if ok else "There was no open run to discard.")
        self.refresh()

    def _on_applied_in_game(self, discipline: str = "") -> None:
        """Register that the driver typed this sheet into GT7.

        Applying a recommendation only writes the SHEET; GT7 can only be updated by the
        driver. This confirmation is therefore the ONLY thing that can make a setup
        active — nothing is able to infer it.

        Confirming "I've entered this in GT7" means the shown recommendation is now on
        the car, so it is FIRST written onto the sheet (exactly as "Apply recommendation"
        does — idempotent if the driver already pressed that button). Without this, a
        driver who read the recommendation, typed it straight into GT7 and confirmed left
        the app's sheet holding the PRE-change values, so the next Analyse re-recommended
        the very changes just made. The recommendation is then consumed.
        """
        import time
        d = discipline or self._discipline
        if str(d).lower() == str(self._discipline).lower():
            vm = self._recommendation_vm()
            if vm is not None:
                self._setups.apply(d, vm.applied_field_values())
        # Phase 2 (closed-loop learning): record this applied change against the
        # session it was based on BEFORE consuming it, so a later run can score
        # whether it helped or hurt — the write side that lets the brain stop
        # re-recommending a change that made the car worse. Best-effort, never blocks.
        self._persist_applied_for_learning(self._last_analysis)
        self._last_analysis = None      # the recommendation is on the car now — consumed
        outcome = self._setups.confirm_applied_in_game(
            d, applied_at=time.strftime("%Y-%m-%d %H:%M"))
        self._garage_status(outcome.reason)
        self.refresh()

    def _persist_applied_for_learning(self, analysis) -> None:
        """Persist a just-applied recommendation so a later run scores it (Phase 2).

        The 'before' session is the most recent recorded session for this car+track
        (the laps the analysis was based on). Scoped by car+track (layout ""), matching
        the scoring trigger + the analyse consume side. Never raises."""
        try:
            if analysis is None or self._db is None:
                return
            changes = list(getattr(analysis, "changes", ()) or ())
            if not changes:
                return
            inp = self._setups.inputs()
            car_name = getattr(inp, "car", "") or ""
            track = getattr(inp, "track", "") or ""
            if not car_name or not track:
                return
            car_id = int(self._db.get_car_id(car_name) or 0)
            if car_id <= 0:
                return
            before = int(self._db.get_previous_session_id(car_id, track, 2_147_483_647) or 0)
            if before <= 0:
                return  # no recorded session yet → nothing to score against later
            from services.setup_learning import persist_applied_recommendation
            persist_applied_recommendation(
                self._db, car_id=car_id, track=track, layout_id="",
                before_session_id=before, changes=changes,
                driver_profile_version=str(getattr(analysis, "driver_profile_version", "") or ""),
                rule_engine_version=str(getattr(analysis, "rule_engine_version", "") or ""))
        except Exception:
            pass

    def _on_lock_setup(self, discipline: str, lock: bool) -> None:
        """Lock (or reopen) a discipline's setup on the active cycle — the explicit
        confirmation the "Lock the base setup" guidance asked for."""
        import time
        d = str(discipline or self._discipline or "race").lower()
        cid = self._runs.active_cycle_id()
        if not cid:
            self._garage_status("Activate an event before locking a setup.")
            return
        if self._db is None or not hasattr(self._db, "lock_setup"):
            self._garage_status("Locking is not available.")
            return
        ok = False
        try:
            ok = bool(self._db.lock_setup(
                cid, d, locked=bool(lock), locked_at=time.strftime("%Y-%m-%d %H:%M")))
        except Exception as exc:
            self._garage_status(f"Could not lock the setup: {exc}")
            return
        if ok:
            self._garage_status(
                f"{d.title()} setup locked for the event." if lock
                else f"{d.title()} setup reopened — you can keep developing it.")
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
            # Qualifying always runs the softest allowed compound (rain tyre when wet) —
            # surface whether the qualifying sheet is on it, naming the specific compound.
            target, current, target_name, current_name, is_wet = self._qualifying_tyre_state()
            confirmed = (current == target) if target else None
            qp.set_readiness(qualifying_vm_from_cc_view(
                view, active_setup_label=label, soft_confirmed=confirmed,
                softest_label=target_name, current_label=current_name, wet=is_wet))
        except Exception:
            pass
        # Qualifying Engineer (Live Activation 2): speak the phase-appropriate cue on each phase
        # edge (prep → out-lap → flying → PB/deleted → cooldown). Silent between edges; only
        # while an authoritative live qualifying run owns the voice.
        self._speak_qualifying_engineer()
        # During the OUT-LAP, give ongoing tyre-temperature guidance so the driver brings the tyres
        # into the optimal window before the flying lap — spoken only when the warm-up status
        # changes (cold → building → up-to-temp), never every tick.
        self._speak_qualifying_tyre_warmup()

    def _qualifying_tyre_state(self):
        """(target_code, current_code, target_name, current_name, is_wet) for the
        qualifying sheet: the compound the qualifying rule wants (softest dry slick, or the
        rain tyre when wet) and what is on the sheet now. Never raises; blanks when
        nothing is resolvable."""
        try:
            from strategy.tyre_selection import resolve_qualifying_compound, current_code
            from data.tyres import get_by_code
            ev = None
            try:
                ev = self._window._build_event_context()
            except Exception:
                ev = None
            target, tname, is_wet, _reason = resolve_qualifying_compound(
                available=getattr(ev, "available_tyres", ()) or (),
                required=getattr(ev, "required_tyres", ()) or (),
                weather=str(getattr(ev, "weather", "") or ""),
                wet_override=self._track_wet)
            try:
                cur = current_code(self._setups.sheet("qualifying").as_dict()) or ""
            except Exception:
                cur = ""
            cname = get_by_code(cur).name if cur and get_by_code(cur) else cur
            return target, cur, tname, cname, is_wet
        except Exception:
            return "", "", "", "", False

    def _apply_qualifying_compound(self) -> None:
        """Put the qualifying compound (softest dry, or the rain tyre when wet) on the
        qualifying sheet — the qualifying rule applied to the setup sheet itself.

        Only touches an ALREADY-AUTHORED sheet and only when it isn't already on the
        target, so it never authors an empty sheet and never churns revisions.
        """
        try:
            from strategy.tyre_selection import setup_fields_for
            sheet = self._setups.sheet("qualifying")
            if not getattr(sheet, "is_authored", False):
                return
            target, current, _t, _c, _wet = self._qualifying_tyre_state()
            if target and current != target:
                fields = setup_fields_for(target)
                if fields:
                    self._setups.apply("qualifying", fields)
        except Exception:
            pass

    def _on_track_wet_toggled(self, wet: bool) -> None:
        """The driver set whether the track is wet — the qualifying tyre override.

        Re-applies the qualifying compound (dry↔wet) and re-feeds, so the setup sheet and
        the Garage follow the change immediately.
        """
        self._track_wet = bool(wet)
        self._apply_qualifying_compound()
        self.refresh()

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
            # Restore the plan the driver approved LAST TIME, so it survives a restart.
            saved = self._approved_strategy()
            if saved.get("candidate_id"):
                if hasattr(sp, "set_selected_plan"):
                    sp.set_selected_plan(str(saved["candidate_id"]))
                if hasattr(sp, "set_status") and not sp._status.text():
                    sp.set_status(f"Your approved plan ({saved.get('name', 'saved plan')}) "
                                  f"is loaded and will be used for the race.")
            # Reflect race readiness so the Start Race control shows where the driver
            # stands before committing to a race.
            if hasattr(sp, "set_race_readiness"):
                ready, blockers = self._race_readiness()
                sp.set_race_readiness(ready, blockers)
        except Exception:
            pass

    def _race_readiness(self) -> tuple:
        """(ready, blockers): whether every stage is complete to start the race.

        Blockers are plain-language and never hard-stop — Start Race can still commit with
        a warning. The point is that the driver, not a telemetry guess, declares the race,
        and does so knowing what (if anything) is still open.
        """
        blockers: list = []
        try:
            if not self._approved_strategy().get("candidate_id"):
                blockers.append("race plan not approved")
        except Exception:
            pass
        try:
            if not self._setups.sheet("race").is_authored:
                blockers.append("race setup not built")
        except Exception:
            pass
        try:
            if not self._has_recorded_run():
                blockers.append("no practice runs recorded")
        except Exception:
            pass
        return (not blockers, tuple(blockers))

    def _approved_strategy(self) -> dict:
        try:
            cid = self._runs.active_cycle_id()
            if cid and self._db is not None and hasattr(self._db, "get_approved_strategy"):
                return dict(self._db.get_approved_strategy(cid) or {})
        except Exception:
            pass
        return {}

    def _recommended_plan_dict(self) -> dict:
        """A show_plan-compatible dict for the RECOMMENDED plan, when none was approved.

        The Live Pit Wall hid its plan card entirely unless the driver had explicitly
        pressed Approve on the Strategy page — so a driver who went straight to the race
        saw "no race plan at all". This falls back to the current recommendation the
        Strategy page is already showing, so the wall always presents *a* plan. It carries
        no ``candidate_id`` (nothing was approved), only the display fields ``show_plan``
        reads.
        """
        try:
            sp = getattr(self._shell, "strategy_page", None)
            vm = getattr(sp, "_vm", None)
            options = list(getattr(vm, "options", ()) or ())
            if not options:
                return {}
            opt = next((o for o in options if getattr(o, "recommended", False)), options[0])
            return {
                "name": getattr(opt, "name", "") or "Recommended plan",
                "total_time": getattr(opt, "total_time", ""),
                "expected_laps": getattr(opt, "expected_laps", ""),
                "pit_windows": getattr(opt, "pit_windows", ""),
                "pit_stops": list(getattr(opt, "pit_stops", ()) or ()),
                "recommended_fallback": True,
            }
        except Exception:
            return {}

    # ---- strategy engine wiring -------------------------------------------

    def _stints_for_engine(self, plan_dict: dict) -> list:
        """Convert an approved plan dict to a list of Stint objects for the engine.

        Reads ``raw_stints`` (persisted by ``_persist_approved_strategy`` when a plan
        result is available in the current session).  Returns [] when the plan lacks
        structured data — callers must guard against an empty list.

        ``ref_lap_ms=0`` is explicitly documented in Stint as "use session best", so
        it is a valid default when no reference lap was recorded.  ``pace_threshold_ms``
        defaults to 2 000 ms (2 s above reference before the tyre-deg alert fires).
        """
        try:
            from strategy.engine import Stint as _Stint
            raw = list(plan_dict.get("raw_stints") or [])
            if not raw:
                return []
            return [
                _Stint(
                    stint_num=i + 1,
                    laps=int((s or {}).get("laps") or 10),
                    compound=str((s or {}).get("compound") or ""),
                    ref_lap_ms=0,
                    pace_threshold_ms=2000,
                )
                for i, s in enumerate(raw)
                if s
            ]
        except Exception:
            return []

    def _push_plan_to_engine(self, plan_dict: dict) -> None:
        """Load an approved plan's stints into the singleton RaceStrategyEngine.

        The engine's ``build_pit_window_response`` / ``build_strategy_response`` etc.
        return "No strategy loaded." until ``set_plan`` is called.  The bridge calls
        this at approval time, on voice acceptance, and defensively in ``_feed_live``.

        Only ``ui/live_shell_bridge.py`` calls ``set_plan`` — ``live_pit_wall.py``
        must never do so (its advisory-only safety test scans that file).
        """
        try:
            eng = getattr(self._window, "_strategy_engine", None)
            if eng is None or not hasattr(eng, "set_plan"):
                return
            stints = self._stints_for_engine(plan_dict)
            if not stints:
                return
            eng.set_plan(stints)
            self._last_engine_plan_key = str(plan_dict.get("candidate_id") or "")
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
            # If we're mapping the pit lane, detect it from the latest out-lap first, so
            # the refreshed session reflects the completed model. While mapping, the pit
            # out-lap recording must NOT read as track-capture (the model is already
            # approved), so refresh ignores the capture controller.
            self._try_map_pit_lane()
            session = self._tracks.refresh(ignore_capture=self._pit_lane_mode)
            # The map redraws every 1 m station, so only build it when the driver is
            # actually looking at this page (it is one of many in the stack) — not on
            # every 750 ms tick from wherever they happen to be.
            map_data = self._track_map_data(session) if page.isVisible() else None
            # Evaluate the recorded laps once, then both SPEAK the engineer's per-lap call
            # (once per new lap) and show it on the page.
            lap_results = self._track_lap_results(session)
            self._voice_track_modelling(session, lap_results)
            page.set_session(session,
                             laps_captured=self._track_laps_captured(),
                             corners=self._track_corners(session),
                             map_data=map_data,
                             capture_note=self._track_capture_note(lap_results))
            # Re-apply a sticky status (e.g. why validation didn't pass) so the 750ms
            # refresh does not wipe it before the driver can read it.
            if self._tm_status:
                self._track_status(self._tm_status)
        except Exception:
            pass

    def _track_laps_captured(self) -> int:
        """Clean laps captured so far, from the capture controller."""
        try:
            ctrl = getattr(self._tracks, "_controller", None)
            if ctrl is not None and hasattr(ctrl, "get_status_summary"):
                s = ctrl.get_status_summary()
                return int(s.get("usable_laps") or s.get("lap_count") or 0)
        except Exception:
            pass
        return 0

    def _track_corners(self, session) -> list:
        try:
            from services.track_modelling_pipeline import corners_for_review
            return corners_for_review(session)
        except Exception:
            return []

    def _controller_lap_count(self) -> int:
        try:
            ctrl = getattr(self._tracks, "_controller", None)
            return len(getattr(getattr(ctrl, "_session", None), "laps", None) or [])
        except Exception:
            return 0

    def _begin_pit_lane_mapping(self) -> None:
        """Approved — now capture one out-lap through the pit lane and map it.

        Restarts capture so the pit lap is recorded; the first completed lap from here is
        detected as the pit-lane lap (the car diverges from the racing line and rejoins)."""
        self._pit_lane_mode = True
        self._pit_lane_baseline_laps = self._controller_lap_count()
        try:
            ctrl = getattr(self._tracks, "_controller", None)
            sess = self._tracks.session
            if ctrl is not None and hasattr(ctrl, "start_session"):
                ctrl.start_session(sess.location_id, sess.layout_id)
        except Exception:
            pass
        self._tm_status = ("Track approved. Now take one lap through the pit lane — in at "
                           "the pit entry, down the lane and back out — and I'll map it. A "
                           "drive-through is enough; you don't need to stop. That completes "
                           "the model.")

    def _try_map_pit_lane(self) -> None:
        """While mapping the pit lane, detect it from the completed out-lap(s).

        The pit lane usually crosses the start/finish line, so the traversal is split
        across two consecutive laps — detect on the last two completed laps stitched
        together. Retry on every new lap until it maps (a warm-up lap before the pit lap
        simply misses once), so the driver isn't forced to pit on a specific lap."""
        if not self._pit_lane_mode:
            return
        try:
            ctrl = getattr(self._tracks, "_controller", None)
            laps = getattr(getattr(ctrl, "_session", None), "laps", None) or []
            if len(laps) <= self._pit_lane_baseline_laps:
                return                                   # no new lap completed yet
            self._pit_lane_baseline_laps = len(laps)     # one attempt per new lap
            result = self._tracks.map_pit_lane(laps[-2:])  # stitch the last two laps
            if result.ok:
                self._pit_lane_mode = False
                if ctrl is not None and hasattr(ctrl, "stop_session"):
                    ctrl.stop_session()
            # A miss (car hasn't been through the pit yet) leaves us in mapping mode to
            # try the next lap; either way surface the engineer's message.
            self._tm_status = result.reason or self._tm_status
        except Exception:
            pass

    def _track_lap_results(self, session) -> list:
        """Per-lap quality results while recording, evaluated live. Raw recorded laps carry
        no quality/path length until a build runs, so evaluate_laps (assess_session_laps)
        is what gives the convergence + callout logic real laps to judge. [] when idle."""
        try:
            if not getattr(session, "capturing", False):
                return []
            ctrl = getattr(self._tracks, "_controller", None)
            if ctrl is not None and hasattr(ctrl, "evaluate_laps"):
                return ctrl.evaluate_laps() or []
        except Exception:
            pass
        return []

    def _track_capture_note(self, results) -> str:
        """The engineer's live capture call for the visual note: whether the last lap
        counted (and why not), and how many clean laps remain — or box now."""
        try:
            from data.track_convergence import lap_modelling_callout
            return lap_modelling_callout(results)
        except Exception:
            return ""

    def _voice_track_modelling(self, session, results) -> None:
        """Speak the engineer's per-lap modelling call and mute lap-time chatter while
        modelling. Fires once per newly completed lap. In VR the driver can't read the
        screen, so this is the primary channel."""
        try:
            announcer = getattr(self._window, "_announcer", None)
            if announcer is None:
                return
            if not bool(getattr(session, "capturing", False)):
                self._tm_last_spoken_lap = 0          # reset for the next capture
                return
            # While modelling, the lap-time announcer is muted (see AnnouncerEventHandler)
            # so the only voice is the modelling call the driver actually needs.
            if hasattr(announcer, "set_session_mode"):
                announcer.set_session_mode("track_modelling")
            n = len(results or [])
            if n > self._tm_last_spoken_lap and n > 0:
                self._tm_last_spoken_lap = n
                from data.track_convergence import lap_modelling_callout
                from voice.announcer import Priority
                text = lap_modelling_callout(results)
                if text and hasattr(announcer, "announce"):
                    announcer.announce(text, Priority.MEDIUM, "track_model_lap",
                                       0.0, interrupt=True)
        except Exception:
            pass

    def _track_map_data(self, session):
        """Drawing primitives for the built track, shown while reviewing AND once the
        model is approved/active — visual proof the shape is mapped. Falls back to the
        on-disk station map when an already-modelled track is selected (no in-memory
        artefact), so the map draws immediately on selection too."""
        try:
            station_map = session.artefact("station_map") if session is not None else None
            if station_map is None and getattr(session, "model_active", False):
                station_map = self._load_station_map_from_disk(session)
            if station_map is None:
                return None
            from ui.track_map_vm import build_track_map_draw_data
            return build_track_map_draw_data(station_map)
        except Exception:
            return None

    def _load_station_map_from_disk(self, session):
        """The accepted track's station map from disk, cached per layout (the file is
        large — don't re-read it every 750 ms tick)."""
        key = (getattr(session, "location_id", ""), getattr(session, "layout_id", ""))
        if key in self._tm_disk_map_cache:
            return self._tm_disk_map_cache[key]
        station_map = None
        try:
            from data.track_station_map import find_station_map_path, import_station_map_json
            path = find_station_map_path(key[0], key[1])
            if path is not None:
                station_map = import_station_map_json(path)
        except Exception:
            station_map = None
        self._tm_disk_map_cache[key] = station_map
        return station_map

    def _on_track_segment(self, row: int, action: str) -> None:
        """A corner-review edit (approve / reject / merge / split) on a table row."""
        result = self._tracks.edit_segment(int(row), str(action))
        self._tm_status = result.reason or ""
        self._feed_track_model()
        if result.reason:
            self._track_status(result.reason)

    def _on_track_segment_rename(self, row: int, new_name: str) -> None:
        result = self._tracks.edit_segment(int(row), "rename", new_name=str(new_name))
        self._tm_status = result.reason or ""
        self._feed_track_model()
        if result.reason:
            self._track_status(result.reason)

    def _on_track_selected(self, location_id: str, layout_id: str) -> None:
        self._tm_status = ""
        result = self._tracks.select_track(location_id, layout_id)
        self._feed_track_model()
        if not result.ok:
            self._tm_status = result.reason
            self._track_status(result.reason)

    def _on_track_action(self, action: str) -> None:
        result = self._tracks.perform(action)
        # A message survives to the next action: a real error stays until recovered, an
        # advisory ("validation didn't pass") stays until the next step changes state.
        self._tm_status = result.reason or ""
        # Drive-until-done: boxing (Stop recording) hands the model straight through
        # build → validate → approve — no per-corner sign-off, no manual steps. If the
        # geometry isn't sound enough yet the work is kept and the driver is told to keep
        # lapping; when it approves, we move on to mapping the pit lane.
        if action == "stop_capture" and result.ok and not self._pit_lane_mode:
            final = self._tracks.auto_finalize()
            self._tm_status = final.reason or self._tm_status
            if final.ok and self._tracks.session.model_active:
                self._begin_pit_lane_mapping()
        self._feed_track_model()
        if self._tm_status:
            self._track_status(self._tm_status)

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
            required, sampled = self._tyre_compound_coverage()
            page.set_map(build_programme_map(
                readiness, next_domain=next_domain,
                tyre_required=required, tyre_sampled=sampled))
        except Exception:
            pass

    def _tyre_compound_coverage(self):
        """(allowed compounds, compounds already sampled) for the tyre-wear area.

        Practice is not complete until every allowed compound has been run — a race can
        force a switch mid-race. Allowed comes from the event; sampled from the dominant
        compound of each run recorded against this event.
        """
        required, sampled = (), set()
        try:
            ev = self._window._build_event_context() if self._window else None
            required = tuple(getattr(ev, "available_tyres", ()) or ())
        except Exception:
            required = ()
        if not required:
            return (), ()          # no restriction → no per-compound requirement
        try:
            for r in self._recorded_runs():
                sid = int(r.get("session_id") or 0)
                if sid and hasattr(self._db, "_dominant_compound"):
                    c = str(self._db._dominant_compound(sid) or "").strip()
                    if c:
                        sampled.add(c.upper())
        except Exception:
            pass
        return required, tuple(sorted(sampled))

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

    def _debrief_session_id(self) -> int:
        """The session the Debrief is about — STRICTLY the active event's last session.

        UAT: the Debrief showed an OLD event, not the active one. It resolved from a
        process-lifetime in-memory id (_last_recorded_session_id) that survives an event
        switch, and never checked the session actually belonged to the active event.

        Resolve only from runs bound to the active preparation cycle, plus the live/just-
        finished session, and verify each candidate's event_id matches the active event
        before returning it. Returns 0 when the active event has no session of its own
        (so the Debrief shows its empty placeholder instead of a stale event)."""
        db = self._db
        active_eid = 0
        try:
            ev = self._window._build_event_context() if self._window else None
            active_eid = int(getattr(ev, "event_id", 0) or 0)
        except Exception:
            active_eid = 0

        def _belongs(sid: int) -> bool:
            if not sid:
                return False
            if active_eid <= 0:
                return True   # no active-event identity to check against — accept
            try:
                meta = db.get_session_meta(sid) if hasattr(db, "get_session_meta") else None
                return int((meta or {}).get("event_id") or 0) == active_eid
            except Exception:
                return False

        # 1. Runs bound to the active preparation cycle (survives a restart), newest first.
        ids = [int(r.get("session_id") or 0) for r in self._recorded_runs()
               if int(r.get("session_id") or 0) > 0]
        for sid in reversed(ids):
            if _belongs(sid):
                return sid
        # 2. The live / just-finished session — only if it is THIS event's.
        live = int(self._live_session_id() or 0)
        if live and _belongs(live):
            return live
        # 3. The most-recent recorded session for THIS event, even if it was never bound
        #    to a preparation cycle — so a practice run's laps stay reviewable (persist)
        #    rather than vanishing when the live session id is gone.
        if active_eid > 0 and hasattr(db, "get_latest_session_for_event"):
            sid = int(db.get_latest_session_for_event(active_eid) or 0)
            if sid:
                return sid
        return 0

    def _feed_debrief(self) -> None:
        try:
            dp = getattr(self._shell, "debrief_page", None)
            db = self._db
            if dp is None or db is None:
                return
            # Per-session debrief: summarise the last recorded session (race or run) —
            # result, pace, consistency, fuel, tyres — so a finished session actually has
            # a debrief. (The old cross-session development scorecard only populates from
            # the setup-experiment loop, which the race flow never drives, so it was
            # always empty here.)
            sid = self._debrief_session_id()
            if sid and hasattr(db, "get_session_laps"):
                review = self._review_for(sid)
                meta, laps = {}, []
                try:
                    if hasattr(db, "get_session_meta"):
                        meta = dict(db.get_session_meta(sid) or {})
                    laps = db.get_session_laps(sid) or []
                except Exception:
                    meta, laps = {}, []
                from ui.shell_feed_adapters import session_debrief_vm
                feedback = getattr(self._window, "_last_feedback_dict", None)
                vm = session_debrief_vm(review, meta, laps=laps, feedback=feedback)
                if vm.has_debrief:
                    dp.set_debrief(vm)
                    return
            # Nothing recorded yet — show the page's own "complete a session" placeholder.
            from ui.components.debrief_view import DebriefVM
            dp.set_debrief(DebriefVM())
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

    def _seed_from_last_applied(self) -> None:
        """Load the last-applied Race and Qualifying tunes onto the sheets ONCE, per scope.

        On open the Garage showed a defaults-only ("standard") sheet even when the driver
        had applied and recorded a setup for this car/track before — the working sheet is
        the only thing startup read, and if it was empty the applied history was ignored.
        Here we mirror ``_seed_sheets``: where the store holds nothing authored for a
        discipline but a past applied revision exists, put the newest revision back on the
        sheet. ``load_revision`` writes the values WITHOUT claiming they are on the car, so
        the driver still re-enters and confirms in GT7 — nothing is silently applied.
        """
        try:
            inputs = self._setups.inputs()
            scope = inputs.scope
            if not inputs.is_known or scope in self._seeded_history:
                return
            self._seeded_history.add(scope)
            for discipline in ("race", "qualifying"):
                if self._sheets.has_setup(scope, discipline):
                    continue
                revs = self._setups.revisions(discipline)
                if not revs:
                    continue
                newest = max(revs, key=lambda r: int(r.get("revision", 0) or 0))
                rev_no = int(newest.get("revision", 0) or 0)
                if rev_no > 0:
                    self._setups.load_revision(discipline, rev_no)
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
            # Order matters: seed the last-applied revision FIRST so it wins. Both seeds
            # are per-scope idempotent and only fill an empty sheet, so if the classic base
            # form seeded first it would shadow the driver's last-applied setup on reopen.
            self._seed_from_last_applied()
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
            self._feed_front_weight_dist(gp)
            self._feed_gearing(gp)
            self._feed_lock(gp)
        except Exception:
            pass

    # ---- per-gear shift strategy -----------------------------------------

    def _feed_shift_strategy(self) -> None:
        """Compute and display the shift strategy for the active setup. Never raises.

        The computation is fast (pure arithmetic, no I/O or AI) so it runs inline
        on the Qt thread rather than on self._spawn.  A failure in any step degrades
        gracefully: the VM builder always returns a safe INSUFFICIENT_EVIDENCE result.
        """
        try:
            sv = getattr(
                getattr(self._shell, "garage_page", None),
                "shift_strategy_view", None)
            if sv is None:
                return
            from strategy.shift_strategy_inputs import (
                resolve_shift_inputs, compute_shift_fingerprint,
                describe_fingerprint_change)
            from strategy.shift_strategy_engine import compute_shift_strategy
            from ui.shift_strategy_vm import build_shift_strategy_vm
            from strategy.setup_engineering import resolve_car_specs
            # FIX D: scope comes from inputs_obj.scope — no need for scope_key import.

            # Inputs — always read from the RACE sheet (gearbox is set up for race,
            # qualifying inherits the same ratios, so strategy uses race as the base).
            inputs_obj = self._setups.inputs()
            car = str(inputs_obj.car or "")
            scope = str(inputs_obj.scope or "")
            sheet = self._setups.sheet("race")
            car_specs = resolve_car_specs(car) if car else {}

            # Active-setup revision — from the authority, zero when unknown.
            active_revision = self._shift_active_revision()

            # Stored data for this scope. Prefer telemetry-calibrated engine data over
            # manually-entered data — a real WOT calibration outranks a hand-typed proxy
            # and lifts the confidence ceiling (Phase 2).
            stored = self._shift_store.get(scope) if scope else None
            engine_data = ((stored or {}).get("calibrated_engine_data")
                           or (stored or {}).get("manual_engine_data") or None)
            req_saving = float((stored or {}).get("required_fuel_saving_pct") or 0.0)
            stored_fp = str((stored or {}).get("fingerprint") or "")

            # Resolve inputs and compute.
            shift_inputs = resolve_shift_inputs(
                sheet, car_specs, active_revision, engine_data)
            result = compute_shift_strategy(
                shift_inputs, required_fuel_saving_pct=req_saving)

            # FIX A.4: compute specific stale text when the fingerprint changed.
            specific_stale = ""
            if stored_fp and stored_fp != result.configuration_fingerprint:
                snap = (stored or {}).get("inputs_snapshot") or {}
                specific_stale = describe_fingerprint_change(shift_inputs, snap)

            vm = build_shift_strategy_vm(
                result,
                profile=self._shift_profile,
                stored_fingerprint=stored_fp if stored_fp else None,
                stale_field_text=specific_stale)
            sv.set_view(vm)
        except Exception:
            pass

    def _shift_active_revision(self) -> int:
        """The active-setup revision for the Race discipline; 0 when not available."""
        try:
            auth = getattr(self._window, "_setup_authority", None)
            if auth is None:
                return 0
            from data.setup_state_authority import SetupIdentity
            ev = (self._window._build_event_context()
                  if hasattr(self._window, "_build_event_context") else None)
            ident = SetupIdentity(
                car=str(getattr(ev, "car", "") or ""),
                track=str(getattr(ev, "track", "") or ""),
                layout_id=str(getattr(ev, "layout_id", "") or ""),
            )
            if hasattr(auth, "active_setup"):
                active = auth.active_setup(ident, "Race")
                return int(getattr(active, "revision", 0) or 0) if active else 0
            if hasattr(auth, "revision_for"):
                return int(auth.revision_for(ident, "Race") or 0)
        except Exception:
            pass
        return 0

    def _on_shift_engine_seeded(self, data: dict) -> None:
        """Persist the seeded manual engine data, then recompute the shift strategy.

        The engine data is saved FIRST, merged onto whatever is already stored, so it
        survives even if the strategy computation below can't run. That matters because
        seeding engine data is usually needed EXACTLY when the car's specs are unknown —
        which is when the computation is insufficient. Previously the save came after the
        computation, so an insufficient/failed compute (e.g. result.qualifying_profile is
        None → .to_dict() raises) silently dropped the engine data the driver just entered.

        The timestamp (computed_at) is injected HERE — the domain and store never
        generate a timestamp.
        """
        try:
            inputs_obj = self._setups.inputs()
            scope = str(inputs_obj.scope or "")
            if not scope:
                self._feed_shift_strategy()
                return

            # 1. Persist the engine data first (merge onto existing stored data).
            stored = self._shift_store.get(scope) or {}
            payload = dict(stored)
            payload["manual_engine_data"] = dict(data or {})

            # 2. Best-effort enrichment: fingerprint, timestamp, snapshot, and the
            #    computed profiles. A failure here must NOT lose the engine data.
            try:
                from datetime import datetime
                from strategy.shift_strategy_inputs import (
                    resolve_shift_inputs, compute_shift_fingerprint, inputs_snapshot)
                from strategy.shift_strategy_engine import compute_shift_strategy
                from strategy.setup_engineering import resolve_car_specs

                car = str(inputs_obj.car or "")
                sheet = self._setups.sheet("race")
                car_specs = resolve_car_specs(car) if car else {}
                active_revision = self._shift_active_revision()
                req_saving = float(payload.get("required_fuel_saving_pct") or 0.0)

                shift_inputs = resolve_shift_inputs(
                    sheet, car_specs, active_revision, dict(data or {}))
                result = compute_shift_strategy(
                    shift_inputs, required_fuel_saving_pct=req_saving)

                payload["fingerprint"] = compute_shift_fingerprint(shift_inputs)
                payload["computed_at"] = datetime.utcnow().isoformat() + "Z"
                payload["inputs_snapshot"] = inputs_snapshot(shift_inputs)
                payload["required_fuel_saving_pct"] = req_saving
                qp = getattr(result, "qualifying_profile", None)
                rp = getattr(result, "race_profile", None)
                if qp is not None and hasattr(qp, "to_dict"):
                    payload["qualifying_profile_json"] = qp.to_dict()
                if rp is not None and hasattr(rp, "to_dict"):
                    payload["race_profile_json"] = rp.to_dict()
            except Exception:
                pass

            self._shift_store.save(scope, payload)
        except Exception:
            pass
        self._feed_shift_strategy()

    def _on_shift_calibrate_requested(self) -> None:
        """Phase 2 — calibrate the torque curve from recorded WOT telemetry.

        Reads the driver's recorded laps for the current car+track, estimates the engine
        torque-curve anchors, and — when the evidence is good enough — persists them as
        ``calibrated_engine_data`` (which ``_feed_shift_strategy`` then prefers over any
        manual entry, lifting the confidence above PROVISIONAL). Reports the outcome on
        the view's calibration status line. Never raises.
        """
        sv = getattr(getattr(self._shell, "garage_page", None),
                     "shift_strategy_view", None)

        def _status(text: str, ok: bool = True) -> None:
            try:
                if sv is not None and hasattr(sv, "set_calibration_status"):
                    sv.set_calibration_status(text, ok=ok)
            except Exception:
                pass

        try:
            # Resolve the numeric car id + track the laps were recorded under.
            car_id = 0
            track = ""
            try:
                if hasattr(self._window, "_current_car_id"):
                    car_id = int(self._window._current_car_id() or 0)
                if hasattr(self._window, "_build_event_context"):
                    track = str(getattr(self._window._build_event_context(), "track", "") or "")
            except Exception:
                pass
            if self._db is None or not hasattr(self._db, "get_laps_with_telemetry"):
                _status("No telemetry database available to calibrate from.", ok=False)
                return
            if not car_id or not track:
                _status("Drive and record a lap for this car and track first — no "
                        "recorded telemetry to calibrate from yet.", ok=False)
                return

            laps = self._db.get_laps_with_telemetry(car_id, track, limit=40) or []
            from strategy.shift_torque_calibration import calibrate_torque_from_laps
            cal = calibrate_torque_from_laps(laps)
            if not cal.ok:
                reason = (cal.warnings[0] if cal.warnings else
                          "Not enough clean full-throttle telemetry to calibrate.")
                _status(reason, ok=False)
                return

            # Persist the calibrated engine data + recompute/persist the profiles so the
            # stored fingerprint and lineage reflect the telemetry source.
            inputs_obj = self._setups.inputs()
            scope = str(inputs_obj.scope or "")
            if scope:
                from datetime import datetime
                from strategy.shift_strategy_inputs import (
                    resolve_shift_inputs, compute_shift_fingerprint, inputs_snapshot)
                from strategy.shift_strategy_engine import compute_shift_strategy
                from strategy.setup_engineering import resolve_car_specs
                car = str(inputs_obj.car or "")
                sheet = self._setups.sheet("race")
                car_specs = resolve_car_specs(car) if car else {}
                active_revision = self._shift_active_revision()
                stored = self._shift_store.get(scope) or {}
                req_saving = float(stored.get("required_fuel_saving_pct") or 0.0)
                engine_data = cal.to_engine_data()
                shift_inputs = resolve_shift_inputs(
                    sheet, car_specs, active_revision, engine_data)
                result = compute_shift_strategy(
                    shift_inputs, required_fuel_saving_pct=req_saving)
                stored.update({
                    "fingerprint": compute_shift_fingerprint(shift_inputs),
                    "computed_at": datetime.utcnow().isoformat() + "Z",
                    "calibrated_engine_data": engine_data,
                    "calibration_json": cal.to_dict(),
                    "inputs_snapshot": inputs_snapshot(shift_inputs),
                    "qualifying_profile_json": result.qualifying_profile.to_dict(),
                    "race_profile_json": result.race_profile.to_dict(),
                    "required_fuel_saving_pct": req_saving,
                })
                self._shift_store.save(scope, stored)

            _status(
                f"Calibrated from telemetry — {cal.confidence.upper()} confidence "
                f"(peak power {cal.peak_power_rpm} rpm, peak torque {cal.peak_torque_rpm} "
                f"rpm, redline {cal.redline} rpm; {cal.sample_count} samples in gear "
                f"{cal.gear_used}). The shift targets below now reflect your car — "
                f"nothing more to enter.", ok=True)
        except Exception:
            _status("Calibration failed — try again after recording a clean lap.", ok=False)
        self._feed_shift_strategy()

    def _on_shift_profile_changed(self, profile: str) -> None:
        """Remember the driver's chosen profile and re-render (no recompute needed)."""
        p = str(profile or "").lower()
        self._shift_profile = p if p in ("qualifying", "race") else "qualifying"
        self._feed_shift_strategy()

    def _on_shift_recalculate(self) -> None:
        """Recompute the shift strategy and persist the result."""
        try:
            from datetime import datetime
            from strategy.shift_strategy_inputs import resolve_shift_inputs, compute_shift_fingerprint
            from strategy.shift_strategy_engine import compute_shift_strategy
            from strategy.setup_engineering import resolve_car_specs

            inputs_obj = self._setups.inputs()
            scope = str(inputs_obj.scope or "")
            if not scope:
                return
            car = str(inputs_obj.car or "")
            sheet = self._setups.sheet("race")
            car_specs = resolve_car_specs(car) if car else {}
            active_revision = self._shift_active_revision()
            stored = self._shift_store.get(scope) or {}
            manual_engine_data = stored.get("manual_engine_data") or None
            req_saving = float(stored.get("required_fuel_saving_pct") or 0.0)

            shift_inputs = resolve_shift_inputs(
                sheet, car_specs, active_revision, manual_engine_data)
            result = compute_shift_strategy(
                shift_inputs, required_fuel_saving_pct=req_saving)

            fingerprint = compute_shift_fingerprint(shift_inputs)
            payload = {
                "fingerprint": fingerprint,
                "computed_at": datetime.utcnow().isoformat() + "Z",
                "manual_engine_data": manual_engine_data or {},
                "qualifying_profile_json": {},
                "race_profile_json":       {},
                "required_fuel_saving_pct": req_saving,
            }
            self._shift_store.save(scope, payload)
        except Exception:
            pass
        self._feed_shift_strategy()

    def _on_shift_go_to_tab(self, tab: str) -> None:
        """Navigate to the Garage and switch to the relevant sub-tab.

        "Transmission"  — navigate to Garage + show the full setup sheet
                          so the driver can enter gear ratios.
        "Shift Strategy" — navigate to Garage + show the Shift Strategy tab
                           (already visible if the driver came from it).
        """
        self._navigate("garage")
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is None:
                return
            if tab == "Shift Strategy":
                if hasattr(gp, "show_shift_strategy_tab"):
                    gp.show_shift_strategy_tab()
            else:
                # Route to the editable Transmission entry group (AREA 2 fix): the driver
                # can now type gear ratios directly instead of landing on the read-only
                # full setup sheet and having nowhere to enter them.
                if hasattr(gp, "show_transmission_group"):
                    gp.show_transmission_group()
                elif hasattr(gp, "_btn_full") and hasattr(gp, "_stack"):
                    # Fallback for any older garage_page without the new tab.
                    gp._btn_full.setChecked(True)
                    gp._stack.setCurrentIndex(1)
        except Exception:
            pass

    def _lock_report_cache(self):
        """The active cycle's preparation report, resolved once per refresh (for lock state)."""
        if self._lock_report is None:
            self._lock_report = {}
            try:
                cid = self._runs.active_cycle_id()
                if cid and self._db is not None and hasattr(self._db, "build_event_preparation_report"):
                    self._lock_report = self._db.build_event_preparation_report(cid) or {}
            except Exception:
                self._lock_report = {}
        return self._lock_report

    def _lock_state(self, discipline: str):
        """(lockable, locked, hint) for a discipline on the active cycle.

        Lockable = the setup has converged enough for a lock to be permitted (the
        engineer's call); locked = the driver has confirmed it. Both come from canonical
        state, never inferred.
        """
        try:
            from strategy.setup_lock import lock_permitted
            from strategy.setup_convergence import SetupConvergenceState
            report = self._lock_report_cache()
            state = str((report.get("setup") or {}).get(discipline) or "")
            lockable = False
            try:
                lockable = lock_permitted(SetupConvergenceState(state)) if state else False
            except Exception:
                lockable = False
            locked = False
            try:
                cid = self._runs.active_cycle_id()
                if cid and hasattr(self._db, "setup_locks"):
                    locked = discipline in (self._db.setup_locks(cid) or ())
            except Exception:
                locked = False
            if locked:
                hint = "This setup is locked for the event. Reopen only if you need to change it."
            elif lockable:
                hint = ("The setup has converged — lock it to mark it final for the event, "
                        "or keep developing.")
            else:
                # NOT lockable yet: say WHY and what unlocks it, so the "Confirm and protect"
                # objective isn't a dead end pointing at a Lock button that isn't shown.
                reason = {
                    "insufficient_evidence": "there aren't enough recorded runs on it yet",
                    "exploring": "it's still being explored — the changes haven't settled",
                    "improving": "it's still improving run to run — not stable yet",
                    "regressed": "the last change made it worse — recover a stable version first",
                }.get(state.lower(), "it hasn't converged yet")
                hint = (f"Not ready to lock: {reason}. Apply this setup, drive and record a few "
                        "consistent runs on it, then confirm in GT7 — the Lock button appears "
                        "once it has converged.")
            return lockable, locked, hint
        except Exception:
            return False, False, ""

    def _lock_objective_discipline(self) -> str:
        """The discipline the engineer's current objective asks to lock, or "".

        The Command Centre can nominate "Lock the base setup" — and "base" has no Garage
        tab of its own, so locking the selected tab never satisfied it and the objective
        was stuck forever. Parsing the objective lets the lock control target exactly what
        the guidance is asking for.
        """
        view = self._last_guidance_view if isinstance(self._last_guidance_view, dict) else {}
        na = view.get("next_action") or {}
        if str(na.get("category") or "").lower() != "lock_setup":
            return ""
        head = str(na.get("headline") or "").lower()
        for d in ("base", "qualifying", "race"):
            if f"the {d} setup" in head:
                return d
        return ""

    def _is_confirm_protect_objective(self) -> bool:
        """True when the current engineer objective is the "confirm and protect" one.

        Detected by keywords in the objective headline — same logic as
        guidance_vm._objective_how_to so they stay in sync without a shared constant.
        """
        view = self._last_guidance_view if isinstance(self._last_guidance_view, dict) else {}
        na = view.get("next_action") or {}
        head = str(na.get("headline") or "").lower()
        return ("protect" in head
                or ("confirm" in head and "setup" in head)
                or "best-known" in head)

    def _feed_lock(self, garage) -> None:
        if not hasattr(garage, "set_lock_state"):
            return
        # Target what the engineer is asking to lock (may be "base", which has no tab),
        # falling back to the selected discipline.
        target = self._lock_objective_discipline() or self._discipline
        lockable, locked, hint = self._lock_state(target)
        if target == "base" and not locked:
            hint = ("The base setup is the foundation both sheets build on. Lock it to "
                    "settle the baseline for the event.")

        # FIX 5b: when the "confirm and protect" objective is active, replace the generic
        # hint with a concrete step checklist so the driver always sees EXACTLY what to do —
        # not a blank space or a vague "keep developing" note.
        if self._is_confirm_protect_objective():
            disc_for_applied = target if target != "base" else self._discipline
            try:
                _label, applied = self._setups.active_setup(disc_for_applied)
            except Exception:
                applied = False
            step1 = (
                "1. Confirmed in GT7 ✓" if applied
                else "1. Press “I’ve entered this in GT7” to confirm this setup is on the car"
            )
            if locked:
                step2 = "2. Setup locked ✓"
            elif lockable:
                step2 = "2. Press “Lock this setup” — it’s ready to lock"
            else:
                step2 = (
                    "2. “Lock this setup” is not yet available — "
                    "drive and record a few consistent runs on this setup first. "
                    "The button appears once it has converged."
                )
            hint = f"{step1}\n{step2}"

        garage.set_lock_state(lockable=lockable, locked=locked, hint=hint,
                              discipline=target,
                              lock_label=f"Lock the {target} setup")

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

    def _build_inputs(self):
        """Build ``SetupInputs``, merging Garage overrides: front-weight-dist and ballast.

        Called by the ``inputs_provider`` lambda every time the setup engine needs context
        (baseline build, analysis, sheet-scope resolution). The front weight distribution
        % the driver entered in the Garage spinbox and the ballast values stored on the
        active discipline sheet are both injected here — the only place that touches the
        frozen dataclass — so the values propagate to every call that reads these fields
        without the domain layer needing to know about the UI.
        """
        from services.setup_inputs import build_setup_inputs
        from dataclasses import replace
        inp = build_setup_inputs(self._db, self._config)
        val = self._front_weight_dist_pct
        if val:
            inp = replace(inp, front_weight_dist_pct=float(val))
        try:
            # Pass the already-built ``inp`` so SetupService.sheet() does NOT call back
            # into self.inputs() -> inputs_provider -> _build_inputs() (infinite recursion
            # that RecursionError-caught, silently ran build_setup_inputs ~1000x per call
            # and lagged the whole app).
            _sheet = self._setups.sheet(self._discipline, inputs=inp)
            _bkg  = float(_sheet.get("ballast_kg", 0.0) or 0.0)
            _bpos = float(_sheet.get("ballast_position", 0.0) or 0.0)
            if _bkg > 0.0:
                inp = replace(inp, ballast_kg=_bkg, ballast_position=_bpos)
        except Exception:
            pass   # fail-safe: zero ballast is the correct default
        return inp

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

    def _feed_front_weight_dist(self, garage) -> None:
        """Reflect the stored front-weight-dist value on the Garage spinbox.

        The 750 ms feed calls this every tick; the ``set_front_weight_dist`` implementation
        guards against clobbering a focused edit and uses blockSignals to avoid re-emitting.
        """
        try:
            if not hasattr(garage, "set_front_weight_dist"):
                return
            val = int(self._front_weight_dist_pct or 0)
            garage.set_front_weight_dist(val)
        except Exception:
            pass

    def _on_front_weight_dist_changed(self, value: int) -> None:
        """Store the user's front weight distribution % for the next baseline build.

        The value is kept in-memory for the session. 0 means "use the drivetrain prior"
        (i.e. send None to the backend). The baseline generator reads this via
        ``_build_inputs()`` which injects it into ``SetupInputs.front_weight_dist_pct``.
        """
        self._front_weight_dist_pct = float(value) if int(value or 0) > 0 else None

    def _on_save_front_weight_dist(self) -> None:
        """Persist the current front weight distribution % to the user's car overlay.

        Guards: no car selected (event not activated), or % is zero/not entered
        (0 means "use drivetrain default" and has nothing to save). The store rejects
        fractions outside the open interval (0, 1), so only 1–99% are accepted.
        """
        try:
            car_name = str(self._setups.inputs().car or "")
        except Exception:
            self._garage_status("No active event — activate an event before saving.")
            return
        pct = self._front_weight_dist_pct   # float or None; None == "use drivetrain prior"
        if not car_name:
            self._garage_status(
                "No car selected — activate an event first so the library knows which car.")
            return
        if not pct or float(pct) <= 0:
            self._garage_status(
                "Enter a front weight % above 0 first — "
                "0 means 'use drivetrain default' and is not saved.")
            return
        ok = self._car_wt_store.set(car_name, pct / 100.0)
        self._car_wt_mod.invalidate()
        if ok:
            self._garage_status(
                f"Saved {int(pct)}% front for {car_name} to the car library.")
        else:
            self._garage_status(
                f"Could not save {int(pct)}% front for {car_name} — "
                "value must be between 1 and 99%.")

    def _on_discipline(self, discipline: str) -> None:
        """Remember the selected discipline and re-feed the Garage for it."""
        d = str(discipline or "").lower()
        if d not in ("qualifying", "race"):
            d = "race"
        self._discipline = d
        self._push_practice_mode(d)
        # Selecting the qualifying sheet applies the qualifying tyre rule to it (softest
        # dry / rain tyre), so the setup sheet is always on the right compound. Guarded to
        # an authored sheet + only-when-different inside the helper, so no churn.
        if d == "qualifying":
            self._apply_qualifying_compound()
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is not None and hasattr(gp, "set_status"):
                gp.set_status("")
        except Exception:
            pass
        self._feed_garage()

    def _on_begin_qualifying(self) -> None:
        """Actually ENTER qualifying — not just show the pit wall.

        Begin Qualifying previously only navigated to the Live Pit Wall, so the app never
        switched to the qualifying setup, never used the qualifying shift RPM, and never
        started push-lap coaching. Now it selects the qualifying discipline (its sheet
        values + qual upshift RPM), asserts an explicit qualifying live mode so the
        runtime beep and the announcer's push-lap coaching use it, re-feeds the Garage,
        then shows the live surface. The setup is not force-applied to GT7 — the driver
        still confirms it in-game — but everything the app controls now reflects
        qualifying.
        """
        self._live_session_mode = "qualifying"
        self._discipline = "qualifying"
        # Reflect the switch in the Garage's own selector so the two never disagree.
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is not None and hasattr(gp, "set_discipline"):
                gp.set_discipline("qualifying")
        except Exception:
            pass
        # Qualifying always runs the softest allowed compound (rain tyre when wet) — put it
        # on the qualifying sheet now, BEFORE pushing the mode so the tracker records the
        # qualifying laps on the right compound.
        self._apply_qualifying_compound()
        # Push the qualifying mode to the runtime (shift RPM + announcer session mode)
        # and the qualifying compound to the tracker, then re-feed the Garage for it.
        self._push_practice_mode("qualifying")
        self._feed_garage()
        self._navigate("live_pit_wall")

    def _on_start_race(self) -> None:
        """Explicitly START THE RACE — the driver's own signal that this is a race.

        Preferred over guessing from telemetry: a practice/qualifying session can look
        like a race, and inferring it would apply the race setup/RPM/plan by mistake. If
        any stage is still open the driver is warned and can confirm; then the app KNOWS
        it is racing and commits the race setup, race shift RPM, and the approved plan.
        """
        ready, blockers = self._race_readiness()
        if not ready and blockers:
            from PyQt6.QtWidgets import QMessageBox
            body = ("Some stages are not complete yet:\n\n  •  "
                    + "\n  •  ".join(blockers)
                    + "\n\nStart the race anyway?")
            answer = QMessageBox.warning(
                self._shell, "Start Race", body,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._enter_race()

    def _enter_race(self) -> None:
        """Commit to race mode: race discipline setup + race shift RPM + the race plan."""
        self._live_session_mode = "race"
        self._discipline = "race"
        try:
            gp = getattr(self._shell, "garage_page", None)
            if gp is not None and hasattr(gp, "set_discipline"):
                gp.set_discipline("race")
        except Exception:
            pass
        self._push_practice_mode("race")
        # Load the plan the app will race to (the approved one, else the recommendation)
        # so the Live Pit Wall shows it and PTT pit queries answer from it.
        try:
            approved = self._approved_strategy() or self._recommended_plan_dict()
            if approved:
                self._live_accepted_plan = approved
                if approved.get("candidate_id"):
                    self._push_plan_to_engine(approved)
        except Exception:
            pass
        self._feed_garage()
        self._navigate("live_pit_wall")

    def _push_practice_mode(self, discipline: str) -> None:
        """Tell the live runtime which discipline is being practised.

        The shift-beep loop in main.py reads window._practice_is_qual_ref /
        _live_mode_ref to pick the qualifying vs race upshift RPM. The new shell never
        wrote them, so a qualifying practice session still beeped at the RACE RPM. The
        selected Garage discipline is now pushed to those refs.
        """
        try:
            # An explicit live session (Begin Qualifying, or a detected race) wins over
            # the plain-practice default; otherwise race-vs-qual follows the selected
            # Garage discipline. Previously this hard-coded "Practice", so the shell could
            # never put the runtime into Qualifying — a qualifying session still beeped at
            # the RACE RPM and the announcer never gave its qualifying push-lap cues.
            if self._live_session_mode == "qualifying":
                mode_str, is_qual = "Qualifying", True
            elif self._live_session_mode == "race":
                mode_str, is_qual = "Race", False
            else:
                mode_str = "Practice"
                is_qual = str(discipline).lower() == "qualifying"
            ref = getattr(self._window, "_practice_is_qual_ref", None)
            if isinstance(ref, list) and ref:
                ref[0] = is_qual
            mode = getattr(self._window, "_live_mode_ref", None)
            if isinstance(mode, list) and mode:
                mode[0] = mode_str
            is_race = (mode_str == "Race")
            # Declare the session type to the WHOLE runtime, mirroring the classic UI
            # (ui/live_ui.py). The new shell only ever wrote the shift-beep refs above, so
            # it left the telemetry tracker on auto-detect — and GT7 auto-classifies any
            # multi-car lobby as a RACE. A baseline practice run then fired "Race started."
            # and framed the pit wall as a live race. Forcing the override keeps a plain
            # practice run a PRACTICE session end-to-end.
            tracker = getattr(self._window, "_tracker", None)
            if tracker is not None and hasattr(tracker, "set_session_type_override"):
                try:
                    from telemetry.state import SessionType
                    tracker.set_session_type_override(
                        SessionType.QUALIFYING if is_qual
                        else SessionType.RACE if is_race
                        else SessionType.PRACTICE)
                except Exception:
                    pass
            # Suppress strategy pit/fuel alerts unless it is an actual race/qualifying.
            engine = getattr(self._window, "_strategy_engine", None)
            if engine is not None:
                if hasattr(engine, "set_race_active"):
                    engine.set_race_active(is_race)
                if hasattr(engine, "set_qualifying_active"):
                    engine.set_qualifying_active(is_qual and not is_race)
            # Keep the announcer's session mode in step — practice / qualifying / race,
            # NOT always "race" (which let a plain practice run speak race calls).
            announcer = getattr(self._window, "_announcer", None)
            if announcer is not None and hasattr(announcer, "set_session_mode"):
                announcer.set_session_mode(mode_str.lower())
        except Exception:
            pass
        self._push_active_compound(discipline)

    def _push_active_compound(self, discipline: str) -> None:
        """Tell the telemetry tracker which compound is on the car for this discipline.

        GT7 does NOT broadcast the tyre compound, so recorded laps take it from
        tracker.set_compound(). Only the classic dashboard's compound dropdown ever
        called it, so a run driven from the new shell recorded a stale/default compound —
        a qualifying run on soft tyres was logged as the race hard the classic default
        still held. The selected discipline's setup compound is now pushed each refresh.

        When the driver has picked a test compound via the run-card selector AND a run is
        open, the test override is used instead of the sheet compound — the saved setup is
        never mutated in that path (AREA 3 contract).
        """
        try:
            tracker = getattr(self._window, "_tracker", None)
            if tracker is None or not hasattr(tracker, "set_compound"):
                return
            from strategy.tyre_selection import current_code
            # Prefer the tyre-test override whenever it is set, regardless of whether
            # a run is open. The previous guard `and self._runs.open_run()` caused the
            # 750ms refresh to clobber the override back to the sheet compound in the
            # window between the driver picking a compound and pressing Start — so the
            # recorded run was tagged with the wrong (sheet) compound (FIX 1b).
            # The override is cleared on record/discard, so subsequent runs always start
            # from the sheet compound unless the driver explicitly picks again.
            if self._test_compound_override:
                code = self._test_compound_override
            else:
                # The compound is a sheet value in its own right — do NOT gate on
                # is_authored (which only looks at numeric fields), or a sheet whose only
                # change is the tyre would never push its compound.
                code = current_code(self._setups.sheet(discipline).as_dict())
            if code:
                tracker.set_compound(code)
        except Exception:
            pass

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
            # Reflect the effective wet state on the "Track is wet" toggle. Switching
            # events clears any leaked driver override so a wet-toggle from a previous
            # event never bleeds onto the next one. For a FIXED-weather event the event
            # decides the condition and the toggle is disabled; only Random Weather relies
            # on the driver's manual signal.
            if hasattr(garage, "set_track_wet"):
                from strategy.tyre_selection import is_wet_weather, is_fixed_weather
                weather = str(getattr(ev, "weather", "") or "")
                # Reset the driver's manual wet override when the EVENT changes — keyed on
                # the event's own identity, NOT the coarse active_cycle_id (which is empty
                # for an unassigned cycle and shared across events, so a 'wet' tick bled
                # onto the next Random event — UAT: 'in garage track is wet but event is
                # random').
                key = str(getattr(ev, "event_id", "") or getattr(ev, "event_name", "") or "")
                if key != self._wet_cycle_id:
                    self._wet_cycle_id = key
                    self._track_wet = None            # different event → drop stale override
                fixed = is_fixed_weather(weather)
                if fixed:
                    self._track_wet = None            # event decides; ignore any override
                    wet = is_wet_weather(weather)
                else:
                    wet = self._track_wet if self._track_wet is not None else False
                garage.set_track_wet(bool(wet), enabled=not fixed)
        except Exception:
            pass

    def _feed_gearing(self, garage) -> None:
        """Load the selected discipline's gear ratios into the Transmission entry group.

        Called from _feed_garage next to _feed_tyres/_feed_shift_rpm. Per-discipline
        separation is automatic: the sheet is keyed by discipline, so Race and Qualifying
        hold independent gearing and the 750ms feed always loads the selected one.
        """
        try:
            if not hasattr(garage, "set_gearing"):
                return
            sheet = self._setups.sheet(self._discipline)
            garage.set_gearing(
                gear_ratios=sheet.gear_ratios,
                final_drive=float(sheet.get("final_drive") or 0.0),
                transmission_max_speed_kmh=float(
                    sheet.get("transmission_max_speed_kmh") or 0.0))
        except Exception:
            pass

    def _on_regulation_changed(self, reg: dict) -> None:
        """Write the series-regulated weight/power onto BOTH discipline sheets — it's a
        car/regulation figure, not a per-discipline tune, so Race and Qualifying share it.
        The vehicle model then reasons from the real regulated car (effective_car_specs)."""
        if not reg:
            return
        last = None
        for disc in ("race", "qualifying"):
            last = self._setups.apply(disc, reg)
            if last.ok:
                self._mirror_to_classic(disc)
        self._garage_status((last.reason if last else "") or "Regulation updated.")
        self.refresh()

    def _on_ballast_changed(self, ballast: dict) -> None:
        """Write the driver's ballast entry (weight + position) onto the selected
        discipline's sheet, through the canonical clamp/authority/persist path — the same
        write as any other setup change. Ballast is a real handling parameter and a common
        regulation requirement (adding weight to meet a series minimum), so it belongs in
        the setup like springs or ARBs."""
        if not ballast:
            return
        outcome = self._setups.apply(self._discipline, ballast)
        if outcome.ok:
            self._mirror_to_classic(self._discipline)
        self._garage_status(outcome.reason or "Ballast updated.")
        self.refresh()

    def _on_gearing_changed(self, gearing: dict) -> None:
        """Write the driver's gear-ratio entry onto the selected discipline's sheet.

        Calls ``self._setups.apply`` so the change goes through the canonical clamp +
        authority + persistence path — the same write path as every other setup change.
        Per-discipline separation is automatic: apply is keyed on self._discipline, so
        Race and Qualifying never share gear values.
        """
        if not gearing:
            return
        outcome = self._setups.apply(self._discipline, gearing)
        if outcome.ok:
            self._mirror_to_classic(self._discipline)
        self._garage_status(outcome.reason or "Gearing updated.")
        self.refresh()

    def _on_car_ranges(self) -> None:
        """Open the per-car min/max ranges editor from the new Garage.

        Classic UI surfaced this via the Setup Builder tab; the new shell had no path
        to it. The dialog itself is unchanged — this just opens it with the current
        car name, and re-runs refresh() when ranges are saved so the next baseline or
        analyse picks them up.
        """
        try:
            from ui.car_ranges_dialog import CarRangesDialog
            car = str(self._setups.inputs().car or "")
            dlg = CarRangesDialog(car, self._shell)
            dlg.ranges_saved.connect(lambda _cn: self.refresh())
            dlg.exec()
        except Exception:
            pass

    def _on_test_compound_change(self, code: str) -> None:
        """Tag the current test run with a different compound WITHOUT modifying the saved setup.

        This is a tyre TEST: the driver wants to lap on a different compound and have the
        laps tagged correctly, but the setup itself (which owns the compound field) must not
        change. So this handler:
          1. calls tracker.set_compound(code) directly — same as _push_active_compound —
             so the telemetry recorder picks up the new compound immediately.
          2. stores _test_compound_override so _push_active_compound prefers it on every
             750ms tick while the run is open.
        It deliberately does NOT call self._setups.apply — the sheet's tyre_front /
        tyre_rear are untouched.
        """
        try:
            code = str(code or "").strip().upper()
            if not code:
                return
            tracker = getattr(self._window, "_tracker", None)
            if tracker is not None and hasattr(tracker, "set_compound"):
                tracker.set_compound(code)
            self._test_compound_override = code
        except Exception:
            pass

    def _feed_run_compound_options(self, rc) -> None:
        """Populate the run-card compound selector with event-allowed compounds.

        Pre-selects the first un-sampled compound (a nudge toward covering all compounds)
        but ONLY on the first call or when the allowed-compound set changes. On every
        subsequent 750ms refresh the selector is left untouched so the driver's pick
        is never overwritten (FIX 1a). The driver can always change their pick — the
        pre-selection is a one-time default, not a lock.
        """
        try:
            if not hasattr(rc, "set_compound_options"):
                return
            from strategy.tyre_selection import build_tyre_choice, current_code
            ev = None
            try:
                ev = self._window._build_event_context()
            except Exception:
                ev = None
            choice = build_tyre_choice(
                discipline=self._discipline,
                available=getattr(ev, "available_tyres", ()) or (),
                required=getattr(ev, "required_tyres", ()) or (),
                race_duration_minutes=float(
                    getattr(ev, "race_duration_minutes", 0) or 0))
            codes = [o.code for o in (choice.options or ())]
            new_codes = tuple(codes)
            self._last_compound_codes = new_codes

            # Pre-select priority — the compound the practice run will be tagged with:
            #   1. the driver's explicit run-card pick (override) — never overwrite it;
            #   2. otherwise the compound of the APPLIED setup, so Practice runs the tyre
            #      the driver actually put on the car. This is what "pull the compound from
            #      the applied setup" means, and it stops the selector from defaulting to a
            #      DIFFERENT compound the driver could confirm by mistake and mis-tag the run;
            #   3. only when the applied setup names no compound does the cover-all-compounds
            #      nudge (first un-sampled) apply.
            # Called every refresh: run_card.set_compound_options guards an open popup and
            # only moves the index when it differs, so the shown compound tracks the applied
            # setup without clobbering a live pick.
            if self._test_compound_override and self._test_compound_override in new_codes:
                preselected = self._test_compound_override
            else:
                applied = (current_code(
                    self._setups.sheet(self._discipline).as_dict()) or "").upper()
                allowed_up = {c.upper() for c in codes}
                if applied and applied in allowed_up:
                    preselected = applied
                else:
                    required, sampled = self._tyre_compound_coverage()
                    sampled_up = {s.upper() for s in sampled}
                    unsampled = [c for c in codes if c.upper() not in sampled_up]
                    preselected = unsampled[0] if unsampled else ""
            rc.set_compound_options(codes, preselected=preselected)
        except Exception:
            pass

    def _track_modelling_active(self) -> bool:
        """True while a track-model capture (or pit-lane mapping) is running. The live
        race/practice engineer voice must stay silent then, so the track-modelling
        callout ('box to map the pit lane') is the only thing spoken — otherwise the
        generic practice line spoke over it (UAT: during track modelling the engineer
        used practice 'clean laps' language and never told me to box for the pit lane)."""
        try:
            if getattr(self, "_pit_lane_mode", False):
                return True
            sess = getattr(getattr(self, "_tracks", None), "session", None)
            return bool(getattr(sess, "capturing", False))
        except Exception:
            return False

    def _feed_live(self) -> None:
        """Feed the Live Pit Wall from the canonical live race state. Never raises.

        Sourcing plan attrs from the window mirrors exactly what the classic
        ``_refresh_audio_engineer`` does (Phase 66 activation).  When they are absent
        the fields remain unknown — never fabricated.
        """
        try:
            lp = getattr(self._shell, "live_page", None)
            if lp is None:
                return
            # Live Activation 1/2/3 (§9): refresh the authoritative recording diagnostics header
            # every tick, whatever the session mode. Whichever discipline currently owns the live
            # recording owns the header — a live Race run (its lap total + phase + pit stops), else a
            # live Qualifying run (its phase + personal best), else the Practice diagnostics.
            if hasattr(lp, "set_diagnostics"):
                _q = getattr(self, "_live_qualifying", None)
                _r = getattr(self, "_live_race", None)
                if _r is not None and _r.is_recording:
                    lp.set_diagnostics(self.live_race_diagnostics())
                elif _q is not None and _q.is_recording:
                    lp.set_diagnostics(self.live_qualifying_diagnostics())
                else:
                    lp.set_diagnostics(self.live_practice_diagnostics())
            from ui.shell_feed_adapters import live_pit_wall_vm_from_state
            from strategy.live_engineer_session import normalise_session_mode
            from strategy.engineer_orchestrator import EngineerContext, orchestrate
            connected = self._connected()
            # The session type gates EVERYTHING that follows. Only an ACTUAL RACE gets the
            # race strategy state, the adaptive pit decision, the pit plan and the "race"
            # framing. A baseline practice or a qualifying run must never look like a live
            # race (UAT: "it told me race started when doing a baseline practice session")
            # — the tracker auto-classifies any multi-car lobby as a race, so gating on the
            # normalised session mode (which honours the explicit practice/qual state) is
            # what keeps a practice run out of the race surface.
            _sess = normalise_session_mode(self._live_session_mode, self._live_race_phase)
            _is_race = (_sess == "race")
            state = None
            audio_view = None
            if _is_race:
                try:
                    tracker = getattr(self._window, "_tracker", None)
                    if tracker is not None and getattr(tracker, "race_type", None) is not None:
                        from strategy.canonical_live_race_state import build_canonical_live_race_state
                        canon = build_canonical_live_race_state(
                            tracker,
                            elapsed_s=getattr(self._window, "_live_race_elapsed_s", None),
                            telemetry_fresh=connected,
                            fuel_per_lap_plan=getattr(self._window, "_live_fuel_plan", None),
                            lap_time_plan_s=getattr(self._window, "_live_pace_plan_s", None),
                            recent_fuel_burn_samples=getattr(self._window, "_live_fuel_samples", None),
                            recent_clean_lap_times_s=getattr(self._window, "_live_clean_lap_times", None),
                            pit_loss_s=getattr(self._window, "_live_pit_loss_s", None),
                            driver_reports=getattr(self._window, "_live_driver_reports", None))
                        state = canon.to_live_strategy_state()
                except Exception:
                    state = None
                # Build the audio-first + adaptive-strategy view ONCE PER LAP, not on every
                # 750ms display tick: the driver's model is "at the end of every lap, are we
                # still optimal?", and recomputing every tick made the replan warning flicker
                # as live figures wobbled AND re-ran the strategy view twice on a lap-signal +
                # timer double-fire. The lap gate reuses the cached decision between laps; KPI
                # (fuel/tyre/lap) still refresh every tick from the fresh state.
                if state is not None:
                    cur_lap = getattr(state, "current_lap", None)
                    stale = (self._live_audio_view is None
                             or cur_lap != self._live_decision_lap
                             or not getattr(state, "telemetry_fresh", True))
                    if stale:
                        try:
                            from strategy.live_audio_strategy_build import build_live_audio_strategy_view
                            self._live_audio_view = build_live_audio_strategy_view(state)
                            decision = (self._live_audio_view or {}).get("strategy_decision") or {}
                            self._live_decision = decision
                            rec = str(decision.get("recommendation") or "")
                            self._live_pending = rec in ("REPLAN_RECOMMENDED", "REPLAN_URGENT")
                            self._live_decision_lap = cur_lap
                        except Exception:
                            self._live_audio_view = None
                    audio_view = self._live_audio_view
            # Session-type-aware engineer via the single Engineer Orchestrator (Phase E):
            # it resolves the mode and returns ONE coordinated line — practice/qualifying
            # talk feel + one-lap pace (never race strategy), race defers to the strategy
            # engine (""). Behaviour matches the previous session_engineer_call (the
            # orchestrator is a parity-tested superset); it is the seam through which the
            # qualifying state machine + live practice brief are activated next. Track
            # modelling keeps its own voice path, so the engineer LINE is computed as before
            # (track_modelling_active left False here) and speaking is gated below.
            _last_s, _best_s = self._live_last_best_lap_s()
            _eng_call = orchestrate(EngineerContext(
                live_session_mode=self._live_session_mode,
                race_phase=self._live_race_phase,
                connected=connected,
                lap_count=self._live_lap_count(),
                last_lap_s=_last_s, best_lap_s=_best_s,
            )).line
            lp.set_state(live_pit_wall_vm_from_state(
                state, connected=connected, audio_view=audio_view,
                race_phase=self._live_race_phase,
                session_mode=_sess,
                engineer_override=_eng_call))
            # Speak it once per new lap (not every 750ms tick) so the engineer's voice
            # tracks the session without chattering — but stay silent during a track-model
            # capture so the track-modelling callout is the only voice the driver hears, and
            # while an authoritative live Qualifying OR Race run owns the voice (its phase cue
            # speaks instead) so the engineers never talk over each other.
            _q = getattr(self, "_live_qualifying", None)
            _r = getattr(self, "_live_race", None)
            _q_owns = _q is not None and _q.is_recording
            _r_owns = _r is not None and _r.is_recording
            if not self._track_modelling_active() and not _q_owns and not _r_owns:
                self._maybe_speak_engineer(_eng_call)
            # The race engineer speaks its phase-edge cue (grid / lights-out / pit / finish),
            # relaying the deterministic strategy advisory on the racing edge — Live Activation 3 §6.
            if _r_owns and not self._track_modelling_active():
                self._speak_race_engineer()
            # Only an actual race shows a pit plan. In practice/qualifying, pass an empty
            # dict so no race-plan card lingers on the wall.
            if hasattr(lp, "show_plan"):
                lp.show_plan((self._live_accepted_plan
                              or self._approved_strategy()
                              or self._recommended_plan_dict()) if _is_race else {})
            # Defensive: if the singleton RaceStrategyEngine has no stints yet (e.g.
            # the app restarted after a plan was approved last session), push the
            # approved plan now so PTT "when do I pit" answers correctly.
            # Guard: only when engine._stints is empty to avoid set_plan() every 750ms.
            try:
                eng = getattr(self._window, "_strategy_engine", None)
                if eng is not None and not getattr(eng, "_stints", True):
                    approved = self._live_accepted_plan or self._approved_strategy()
                    plan_key = str(approved.get("candidate_id") or "")
                    if plan_key and plan_key != self._last_engine_plan_key:
                        self._push_plan_to_engine(approved)
            except Exception:
                pass
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
            # Read the real window attribute (``_config_path``) first; fall back to the
            # test-fake name. An empty/absent path means "do not persist" (tests), so skip
            # rather than resolving a real path and polluting. NOTE the arg order:
            # save_config(path, config) — the previous call had them swapped, so the
            # write silently failed even when a path was present.
            path = getattr(self._window, "_config_path", None)
            if path is None:
                path = getattr(self._window, "config_path", None)
            if not path:
                return
            config_paths.save_config(str(path), self._config)
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
        # Fold the driver's handling verdict from Review into the analysis. The brain
        # reads the structured dropdowns NATIVELY (balance, braking, rotation, gearing,
        # traction, kerbs); only the free-text notes go through the text path. Without
        # this the brain sees telemetry symptoms only, so an understeer felt by the
        # driver on a car with clean telemetry would falsely read "inside its window".
        feedback = dict(getattr(self, "_last_feedback", None) or {})
        notes = str(feedback.get("notes") or "").strip()
        self._spawn(lambda: self._analysis_done.emit(self._setups.analyse(
            discipline, feeling=notes, feedback=feedback or None,
            live_corner_aggregates=self._live_corner_aggregates())))

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
    def _reset_context_caches(self) -> None:
        """Clear every per-event / per-run cache in ONE place so switching, creating or
        finishing an event cannot leave a page rendering the previous event's data.

        Program 3 (Phase D3): the three switch/finish handlers previously each carried
        their OWN copy of this list, so a newly-added cache was easy to forget in one of
        them — the exact drift the UI audit flagged, and this now also clears the
        per-cycle caches (_runs_cache / _run_discipline / _lock_report) the old block
        missed, which could show the previous event's runs/lock state on the first tick
        after a switch. Every field here is rebuilt on the next refresh() tick, so
        clearing is safe. The active event has already changed in config, so any
        in-flight background worker is rejected by the existing nav-key guard."""
        self._review_cache.clear()
        self._runs_cache = None
        self._run_discipline = {}
        self._lock_report = None
        self._last_analysis = None
        self._live_accepted_plan = None
        self._live_audio_view = None
        self._live_decision_lap = None
        self._live_decision = None
        self._live_pending = False
        self._last_guidance_view = None
        self._last_engine_plan_key = ""
        self._test_compound_override = None
        self._last_compound_codes = ()

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
        self._reset_context_caches()
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
        self._reset_context_caches()
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
        # Keep the driver's handling verdict so the next Analyse can weigh it
        # (the Garage "Analyse" otherwise sees telemetry symptoms only).
        self._last_feedback = dict(feedback or {})
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

    def _on_select_plan(self, key: str) -> None:
        """The driver chose a plan other than the recommended one. The recommendation is
        advice; the choice is theirs, and it is what Approve then commits."""
        sp = getattr(self._shell, "strategy_page", None)
        if sp is None:
            return
        try:
            sp.set_selected_plan(str(key or ""))
            name = next((o.name for o in sp._vm.options if o.key == key), "")
            sp.set_status(f"{name} is your plan — approve it to take it to the pit wall."
                          if name else "")
        except Exception:
            pass

    def _on_approve_strategy(self) -> None:
        """Approve the race plan the driver has chosen and move to the live wall.

        Records approval if the window supports it; never mutates a setup. The chosen
        plan defaults to the recommended one until the driver picks a different card.
        """
        chosen = ""
        try:
            sp = getattr(self._shell, "strategy_page", None)
            chosen = sp.selected_plan() if sp is not None else ""
        except Exception:
            chosen = ""
        # Persist the chosen plan on the cycle so it is still the plan next launch.
        self._persist_approved_strategy(chosen)
        try:
            window = self._window
            fn = getattr(window, "approve_race_plan", None)
            if callable(fn):
                try:
                    fn(chosen) if chosen else fn()
                except TypeError:      # older signature takes no argument
                    fn()
        except Exception:
            pass
        # Stay on the Strategy page after approving. Approving the plan is NOT starting
        # the race — "Start Race" is the explicit next step, and its readiness caption
        # lives here. Jumping to the Pit Wall stranded that forward action a page away
        # (the driver had to navigate back to actually start). Approve → Start Race is now
        # a straight line; Start Race is what opens the Live Pit Wall.
        try:
            sp = getattr(self._shell, "strategy_page", None)
            if sp is not None and hasattr(sp, "set_status"):
                sp.set_status("Plan approved. Press Start Race when you're ready to go.")
        except Exception:
            pass
        self.refresh()

    def _persist_approved_strategy(self, candidate_id: str) -> None:
        """Save the approved plan's essentials on the cycle so it reloads next launch.

        Also enriches the persisted dict with ``raw_stints`` (list of
        ``{laps, compound}`` dicts) when the plan result from the current session is
        available.  ``_stints_for_engine`` reads ``raw_stints`` to build Stint objects;
        without it the engine stays empty and PTT "when do I pit" returns the fallback
        message.
        """
        import time
        plan = {}
        try:
            cid = self._runs.active_cycle_id()
            if not cid or self._db is None or not hasattr(self._db, "save_approved_strategy"):
                return
            sp = getattr(self._shell, "strategy_page", None)
            opt = None
            for o in (getattr(sp, "_vm", None).options if sp is not None else ()):
                if o.key == candidate_id or (not candidate_id and o.recommended):
                    opt = o
                    break
            plan = {"approved_at": time.strftime("%Y-%m-%d %H:%M")}
            if opt is not None:
                plan.update({
                    "candidate_id": opt.key, "name": opt.name,
                    "total_time": opt.total_time, "expected_laps": opt.expected_laps,
                    "pit_windows": opt.pit_windows, "tyres": opt.tyre_sequence,
                    "stints": list(opt.stints), "pit_stops": list(opt.pit_stops),
                })
            # Enrich with raw, engine-compatible stint data (laps + compound code) from
            # the live plan result so PTT can answer "when do I pit" via
            # RaceStrategyEngine.  Only available in the current session; a reloaded
            # plan from DB carries its raw_stints from the previous persist call.
            try:
                result = getattr(getattr(self._plans, "last_plan", None), "result", None)
                if result is not None and opt is not None:
                    from ui.race_strategy_vm import _find_candidate
                    cand = _find_candidate(result, opt.key)
                    if cand is not None:
                        laps_per = list(getattr(cand, "estimated_laps_per_stint", []) or [])
                        comp_plan = list(getattr(cand, "compound_plan", []) or [])
                        raw = [
                            {"laps": int(laps_per[i]),
                             "compound": comp_plan[i] if i < len(comp_plan) else ""}
                            for i in range(len(laps_per))
                        ]
                        if raw:
                            plan["raw_stints"] = raw
            except Exception:
                pass
            self._db.save_approved_strategy(cid, plan)
        except Exception:
            pass
        # Push the plan into the singleton engine so PTT pit-window queries work.
        # (Defensive: guard the engine push outside the DB block so a DB failure
        # does not prevent the engine from being primed for this session.)
        if plan:
            self._push_plan_to_engine(plan)

    def _on_debrief_action(self, key: str) -> None:
        try:
            k = (key or "").lower()
            # The debrief is the terminal programme stage; closing it FINISHES the event
            # (with the same confirmation as Home's Finish this event).
            if k == "close":
                self._on_finish_event()
                return
            dest = {"to_qualifying": "qualifying", "to_race": "race_strategy",
                    "prepare_qualifying": "qualifying", "prepare_race": "race_strategy",
                    "continue": "garage", "post_review": "engineering_library"}.get(
                k, "home")
            self._navigate(dest)
        except Exception:
            pass

    def _on_finish_event(self) -> None:
        """Home 'Finish this event' — confirm, then mark the active event complete.

        Finishing clears the active event and its live/review caches — heavier than the
        neighbouring "switch"/"create" controls — so it confirms first, mirroring the
        Start Race warning.
        """
        try:
            from PyQt6.QtWidgets import QMessageBox
            answer = QMessageBox.warning(
                self._shell, "Finish event",
                "Finish and close this event? Preparation for it stops and it is no "
                "longer the active event.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        except Exception:
            pass
        self._finish_active_event()

    def _finish_active_event(self) -> None:
        """Complete the active event through the headless service, then return Home.

        Clears the live/review caches so nothing from the finished event bleeds into the
        next one, mirroring the reset done on an event switch.
        """
        try:
            result = self._events.complete_active_event()
        except Exception:
            result = None
        if result is not None:
            self._guidance_status(result.message or "")
        self._reset_context_caches()
        self._navigate("home")
        self.refresh()

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
