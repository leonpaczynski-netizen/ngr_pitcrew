"""Race Plan surface — mixin for MainWindow (decomposition slice 3).

Extracted verbatim from ui/dashboard.py: the deterministic, evidence-based Race
Plan group (Groups 48-51) plus the Sprint-10 Practice->Strategy hand-off
(PracticeEvidenceBundle) surface. Every method operates on the shared MainWindow
``self`` (db, event context, strategy engine, bridge, and shared helpers
_build_strategy_inputs/_resolve_strat_session_id/_load_car_specs_for_current/
_group_style resolve via the MRO), so behaviour is unchanged. Does not import
ui.dashboard (keeps the base-class import acyclic). The interleaved live-replan /
road-distance methods are a separate concern and stay in dashboard.py.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt  # noqa: F401
from PyQt6.QtWidgets import (  # noqa: F401
    QGroupBox, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QDoubleSpinBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView,
)

# Module-level display constants — must match dashboard.py
_DARK_CARD = "#2A2A2A"
_TEXT = "#E0E0E0"


class RacePlanMixin:
    """Race Plan + Practice->Strategy hand-off surface for MainWindow."""

    def _build_race_plan_group(self) -> QGroupBox:
        """Deterministic, evidence-based Race Plan surface (Groups 48/49/50).

        Runs the pure strategy engine over the current event settings + selected
        SessionDB session — NO API key, NO setup Apply/approve controls, NO writes.
        Read-only presentation of the recommended plan, confidence, stint plan,
        candidate comparison, evidence sources, missing evidence, and risks.
        """
        box = QGroupBox("Race Plan (evidence-based — no AI, no API key)")
        box.setStyleSheet(self._group_style())
        v = QVBoxLayout(box)

        intro = QLabel(
            "Builds a race strategy from your event settings and — when a practice "
            "session is loaded — your measured SessionDB laps. Ranked by estimated "
            "TOTAL race time, not fastest lap. Read-only: this never changes or "
            "applies a car setup."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #AAA; font-size: 11px; padding: 2px;")
        v.addWidget(intro)

        # --- Group 51: read-only session selector + diagnostics/readiness ---
        sess_row = QHBoxLayout()
        sess_row.addWidget(QLabel("Session:", styleSheet=f"color: {_TEXT};"))
        self._rp_session_combo = QComboBox()
        self._rp_session_combo.setToolTip(
            "Choose which recorded practice session the race plan reads (read-only). "
            "'Active session (auto)' uses the currently resolved session.")
        self._rp_session_combo.addItem("Active session (auto)", 0)
        self._rp_session_combo.currentIndexChanged.connect(
            lambda _=0: self._refresh_race_plan_diagnostics())
        sess_row.addWidget(self._rp_session_combo, 1)
        self._btn_rp_refresh_sessions = QPushButton("Refresh")
        self._btn_rp_refresh_sessions.setToolTip("Reload the list of recent sessions for this car and track.")
        self._btn_rp_refresh_sessions.clicked.connect(self._populate_race_plan_sessions)
        sess_row.addWidget(self._btn_rp_refresh_sessions)
        v.addLayout(sess_row)

        self._rp_session_status = QLabel("No session selected.")
        self._rp_session_status.setWordWrap(True)
        self._rp_session_status.setStyleSheet("color: #AAA; font-size: 11px; padding: 1px;")
        v.addWidget(self._rp_session_status)

        self._rp_readiness_status = QLabel("Race Plan readiness: —")
        self._rp_readiness_status.setWordWrap(True)
        self._rp_readiness_status.setStyleSheet("color: #F5C542; font-size: 11px; padding: 1px;")
        v.addWidget(self._rp_readiness_status)

        # Small manual inputs Group 49 needs but cannot infer (shown as manual input).
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_style = f"color: {_TEXT};"

        self._rp_pit_loss = QDoubleSpinBox()
        self._rp_pit_loss.setRange(0.0, 120.0)
        self._rp_pit_loss.setDecimals(1)
        self._rp_pit_loss.setSingleStep(0.5)
        # UAT: seed from the persisted strategy pit loss so the field shows the real
        # value (e.g. 20s) instead of 0. The strategy math already used the config
        # value; the field just never reflected it. Re-synced on tab show via
        # _sync_race_plan_pit_loss.
        self._rp_pit_loss.setValue(self._config_pit_loss_secs())
        self._rp_pit_loss.setToolTip(
            "Pit-lane time loss in seconds (entry to racing line). Seeded from the "
            "event/strategy value; edit to override for this plan.")
        form.addRow(QLabel("Pit loss (s):", styleSheet=lbl_style), self._rp_pit_loss)

        self._rp_start_fuel = QDoubleSpinBox()
        self._rp_start_fuel.setRange(1.0, 100.0)
        self._rp_start_fuel.setDecimals(0)
        self._rp_start_fuel.setSingleStep(5.0)
        self._rp_start_fuel.setValue(100.0)
        self._rp_start_fuel.setToolTip("Starting fuel as a percentage of a full tank (GT7 full = 100).")
        form.addRow(QLabel("Starting fuel (%):", styleSheet=lbl_style), self._rp_start_fuel)
        v.addLayout(form)

        from ui import ngr_theme as _ngr
        btn_row = QHBoxLayout()
        self._btn_build_race_plan = QPushButton("Build Race Strategy")
        # Primary CTA of this read-only surface: it COMPUTES a plan (never applies
        # a setup or calls a pit), so the neon-green primary style is appropriate.
        self._btn_build_race_plan.setStyleSheet(_ngr.primary_button_qss())
        self._btn_build_race_plan.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_build_race_plan.setToolTip(
            "Generate an evidence-based race strategy from the current event + "
            "session data. No API key required. Cannot change any car setup.")
        self._btn_build_race_plan.clicked.connect(self._run_race_plan)
        # Sprint 10: explicit Practice → Strategy hand-off. Builds a
        # PracticeEvidenceBundle from the selected practice session (measured
        # evidence + the applied-in-GT7 setup checkpoint) and plans from it,
        # surfacing confidence, missing evidence, and any staleness.
        self._btn_race_plan_from_practice = QPushButton("Build Race Plan from This Practice")
        self._btn_race_plan_from_practice.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_race_plan_from_practice.setStyleSheet(
            "background:#143A5C; color:#CFE8FF; font-weight:bold; "
            "border:1px solid #2E6FA8; padding:6px 14px;")
        self._btn_race_plan_from_practice.setToolTip(
            "Bundle this practice session's measured evidence and the setup you "
            "confirmed applied in GT7, then build the race plan from it. Warns when "
            "the evidence is thin or the setup was never confirmed in game.")
        self._btn_race_plan_from_practice.clicked.connect(self._run_race_plan_from_practice)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_race_plan_from_practice)
        btn_row.addWidget(self._btn_build_race_plan)
        v.addLayout(btn_row)

        self._race_plan_text = QTextEdit()
        self._race_plan_text.setReadOnly(True)
        self._race_plan_text.setMinimumHeight(240)
        # Read-only advisory output — cool teal left-edge signals "information",
        # not an action surface.
        self._race_plan_text.setStyleSheet(
            f"background: {_DARK_CARD}; color: {_TEXT}; "
            f"border: 1px solid #444; border-left: 3px solid {_ngr.ADVISORY_EDGE};")
        self._race_plan_text.setPlaceholderText(
            "Click Build Race Strategy to generate an evidence-based race plan. "
            "Load a practice session for higher confidence.")
        v.addWidget(self._race_plan_text)

        from ui.race_strategy_vm import CANDIDATE_TABLE_COLUMNS
        self._race_plan_table = QTableWidget()
        self._race_plan_table.setColumnCount(len(CANDIDATE_TABLE_COLUMNS))
        self._race_plan_table.setHorizontalHeaderLabels(CANDIDATE_TABLE_COLUMNS)
        self._race_plan_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._race_plan_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._race_plan_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._race_plan_table.setAlternatingRowColors(True)
        # Inherit the polished global NGR table styling (dark header, carbon rows,
        # neon selection) instead of a one-off inline style — keeps the pit-wall
        # candidate table consistent with every other table in the app.
        self._race_plan_table.setMinimumHeight(140)
        v.addWidget(QLabel("Candidate comparison (legal strategies, ranked by total race time):",
                           styleSheet="color:#AAA; font-size:11px; padding-top:4px;"))
        v.addWidget(self._race_plan_table)

        # Group 52/53: read-only Live Replan Readiness surface. Reads live race state
        # (read-only), compares it to the pre-race plan, and shows an ADVISORY snapshot.
        # No auto-refresh loop, no pit call, no voice, no Apply — refresh is manual.
        _replan_box = QGroupBox("Live Replan Readiness (read-only, advisory only)")
        _replan_box.setStyleSheet(self._group_style())
        _rv = QVBoxLayout(_replan_box)

        # Persistent advisory-only tag so this surface can never be mistaken for a
        # pit command — reinforces the copy in the group title.
        _replan_tag_row = QHBoxLayout()
        _replan_tag = _ngr.status_badge("ADVISORY ONLY · NO PIT COMMAND", "advisory")
        _replan_tag_row.addWidget(_replan_tag, 0, Qt.AlignmentFlag.AlignLeft)
        _replan_tag_row.addStretch()
        _rv.addLayout(_replan_tag_row)

        _replan_row = QHBoxLayout()
        self._btn_rp_replan_refresh = QPushButton("Refresh Live Replan Snapshot")
        # A read action (reads live state), never an apply — quiet secondary style.
        self._btn_rp_replan_refresh.setStyleSheet(_ngr.secondary_button_qss())
        self._btn_rp_replan_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_rp_replan_refresh.setToolTip(
            "Read the current live race state (read-only) and check whether the "
            "pre-race plan is still on track. Advisory only — no pit call, no setup "
            "change, no API key.")
        self._btn_rp_replan_refresh.clicked.connect(self._refresh_live_replan_snapshot)
        _replan_row.addStretch()
        _replan_row.addWidget(self._btn_rp_replan_refresh)
        _rv.addLayout(_replan_row)

        try:
            from strategy.race_strategy_replan import replan_placeholder_message
            _replan_msg = replan_placeholder_message()
        except Exception:
            _replan_msg = "Live Replan Readiness: not connected yet."
        self._rp_replan_status = QLabel(_replan_msg)
        self._rp_replan_status.setWordWrap(True)
        # Cool advisory panel styling — visibly read-only, distinct from actions.
        self._rp_replan_status.setStyleSheet(_ngr.banner_qss("advisory"))
        _rv.addWidget(self._rp_replan_status)

        v.addWidget(_replan_box)

        return box

    # NOTE: _config_pit_loss_secs deliberately stays on MainWindow in dashboard.py
    # (it is the sole config["strategy"] access in this surface and is pinned by
    # the frozen fan-out allowlist); it resolves here via the MRO.

    def _sync_race_plan_pit_loss(self) -> None:
        """Re-seed the Race Plan pit-loss field from config on tab show, unless the
        driver has set a non-zero override (preserve a deliberate manual value)."""
        if not hasattr(self, "_rp_pit_loss"):
            return
        if self._rp_pit_loss.value() <= 0.0:
            self._rp_pit_loss.setValue(self._config_pit_loss_secs())

    def _assemble_race_plan_inputs(self) -> dict:
        """Collect deterministic strategy inputs from event context + session.

        Read-only. Reads canonical EventContext for race settings, the resolved
        practice session id, the car id, and the two small manual fields. pit loss
        falls back to the frozen strategy snapshot when the manual field is 0.
        Never raises.
        """
        ec = self._build_event_context()
        try:
            session_id = int(self._selected_race_plan_session_id())
        except Exception:
            session_id = 0

        car_name = ""
        car_id = 0
        try:
            car_name, _ = self._load_car_specs_for_current()
            if self._db and car_name:
                car_id = int(self._db.get_car_id(car_name) or 0)
        except Exception:
            car_id = 0

        # Pit loss: manual field wins; else the frozen snapshot's pit_loss_secs.
        pit_loss = float(self._rp_pit_loss.value()) if hasattr(self, "_rp_pit_loss") else 0.0
        pit_loss_is_manual = pit_loss > 0
        if not pit_loss_is_manual:
            try:
                _snap = self._build_strategy_inputs()
                pit_loss = float(_snap.race_params_dict().get("pit_loss_secs", 0.0) or 0.0)
            except Exception:
                pit_loss = 0.0

        start_fuel = float(self._rp_start_fuel.value()) if hasattr(self, "_rp_start_fuel") else 100.0

        race_type = getattr(ec, "race_type", "lap")
        return {
            "event_context": ec,
            "session_id": session_id,
            "car_id": car_id,
            "car_name": car_name,
            "track": str(getattr(ec, "track", "") or ""),
            "layout_id": str(getattr(ec, "layout_id", "") or ""),
            "race_type": race_type,
            "race_laps": int(getattr(ec, "laps", 0) or 0) if race_type != "timed" else 0,
            "race_duration_minutes": float(getattr(ec, "race_duration_minutes", 0) or 0) if race_type == "timed" else 0.0,
            "fuel_multiplier": float(getattr(ec, "fuel_multiplier", 0.0) or 0.0),
            "tyre_multiplier": float(getattr(ec, "tyre_wear_multiplier", 0.0) or 0.0),
            "refuel_rate_lps": float(getattr(ec, "refuel_rate_lps", 0.0) or 0.0),
            "pit_loss_seconds": pit_loss,
            "pit_loss_is_manual": pit_loss_is_manual,
            "starting_fuel_pct": start_fuel,
            "available_compounds": tuple(getattr(ec, "available_tyres", ()) or ()),
            "required_compounds": tuple(getattr(ec, "required_tyres", ()) or ()),
            "mandatory_pit_stops": int(getattr(ec, "mandatory_stops", 0) or 0),
        }

    def _selected_race_plan_session_id(self) -> int:
        """Session id chosen in the Race Plan selector, or the resolved active one.

        The combo's first entry ("Active session (auto)", data=0) means "use the
        currently resolved practice session". Any other entry carries its session
        id in the item data. Read-only; never raises.
        """
        try:
            combo = getattr(self, "_rp_session_combo", None)
            if combo is not None:
                data = combo.currentData()
                sid = int(data) if data is not None else 0
                if sid > 0:
                    return sid
            return int(self._resolve_strat_session_id() or 0)
        except Exception:
            return 0

    def _populate_race_plan_sessions(self) -> None:
        """Fill the session selector with recent sessions for this car+track (read-only)."""
        combo = getattr(self, "_rp_session_combo", None)
        if combo is None:
            return
        try:
            from ui.race_strategy_readiness_vm import list_recent_matching_sessions
            ec = self._build_event_context()
            track = str(getattr(ec, "track", "") or "")
            car_id = 0
            try:
                car_name, _ = self._load_car_specs_for_current()
                if self._db and car_name:
                    car_id = int(self._db.get_car_id(car_name) or 0)
            except Exception:
                car_id = 0
            sessions = list_recent_matching_sessions(self._db, car_id, track, limit=10)

            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Active session (auto)", 0)
            for s in sessions:
                combo.addItem(s.label, s.session_id)
            combo.blockSignals(False)
        except Exception:
            # Never break the UI — leave the default entry in place.
            try:
                combo.blockSignals(False)
            except Exception:
                pass
        self._refresh_race_plan_diagnostics()

    def _refresh_race_plan_diagnostics(self) -> None:
        """Update the session-status + readiness labels for the selected session.

        Read-only: reads SessionDB samples via the adapter and grades readiness.
        Never builds a plan, never writes, never raises.
        """
        try:
            from strategy.race_strategy_session_adapter import extract_session_strategy_samples
            from ui.race_strategy_readiness_vm import (
                build_session_diagnostics, build_race_plan_readiness,
            )
            inp = self._assemble_race_plan_inputs()
            samples = extract_session_strategy_samples(
                self._db, inp["session_id"],
                expected_car_id=inp["car_id"], expected_track=inp["track"],
                layout_id=inp["layout_id"],
            )
            diag = build_session_diagnostics(
                samples, event_car_id=inp["car_id"], event_track=inp["track"],
                event_layout=inp["layout_id"],
            )
            readiness = build_race_plan_readiness(samples=samples, event_settings=inp)
            if hasattr(self, "_rp_session_status"):
                self._rp_session_status.setText(diag.message)
            if hasattr(self, "_rp_readiness_status"):
                self._rp_readiness_status.setText(
                    f"{readiness.readiness_message}. Next: {readiness.next_best_action}")
        except Exception:
            if hasattr(self, "_rp_session_status"):
                self._rp_session_status.setText("Session diagnostics unavailable.")

    def _run_race_plan(self) -> None:
        """Build and render an evidence-based race plan (no AI, no Apply)."""
        from ui.race_strategy_vm import (
            run_race_plan_from_session, build_race_plan_view_model,
            render_race_plan_html, candidate_table_rows,
        )
        from strategy.race_strategy_session_adapter import extract_session_strategy_samples
        from ui.race_strategy_readiness_vm import (
            build_session_diagnostics, build_race_plan_readiness,
            render_readiness_html, empty_state_messages,
        )
        try:
            inp = self._assemble_race_plan_inputs()
        except Exception as exc:
            self._race_plan_text.setHtml(
                f"<p style='color:#E8A9A3;'>Could not read race settings: {exc}</p>")
            return

        # Rear-fragility from the structured driver profile (never free text).
        rear_fragile = False
        try:
            from strategy.setup_driver_profile import build_driver_profile
            _p = build_driver_profile()
            rear_fragile = bool(_p.prefers_rear_stability or _p.dislikes_snap_exit)
        except Exception:
            rear_fragile = False

        # Weather source label for the evidence display (manual pit loss noted below).
        try:
            from strategy.race_strategy_pipeline import recommend_strategy_from_session
            _result = recommend_strategy_from_session(
                self._db,
                session_id=inp["session_id"],
                car_id=inp["car_id"],
                track=inp["track"],
                layout_id=inp["layout_id"],
                race_duration_minutes=inp["race_duration_minutes"],
                race_laps=inp["race_laps"],
                fuel_multiplier=inp["fuel_multiplier"],
                tyre_multiplier=inp["tyre_multiplier"],
                refuel_rate_lps=inp["refuel_rate_lps"],
                pit_loss_seconds=inp["pit_loss_seconds"],
                starting_fuel_pct=inp["starting_fuel_pct"],
                available_compounds=inp["available_compounds"],
                required_compounds=inp["required_compounds"],
                mandatory_pit_stops=inp["mandatory_pit_stops"],
                rear_traction_fragile=rear_fragile,
            )
            vm = build_race_plan_view_model(_result)
            # Group 53: retain the read-only pre-race result + event inputs so the
            # Live Replan snapshot can compare live state against this plan.
            self._last_race_plan_result = _result
            self._last_race_plan_inputs = dict(inp)
        except Exception as exc:
            self._race_plan_text.setHtml(
                f"<p style='color:#E8A9A3;'>Race plan could not be built: {exc}</p>")
            return

        # Group 51: readiness + diagnostics banner above the plan, plus honest
        # empty/missing-evidence guidance. All read-only, evidence-based.
        readiness_html = ""
        empty_html = ""
        try:
            samples = extract_session_strategy_samples(
                self._db, inp["session_id"],
                expected_car_id=inp["car_id"], expected_track=inp["track"],
                layout_id=inp["layout_id"],
            )
            diag = build_session_diagnostics(
                samples, event_car_id=inp["car_id"], event_track=inp["track"],
                event_layout=inp["layout_id"],
            )
            readiness = build_race_plan_readiness(samples=samples, event_settings=inp)
            readiness_html = render_readiness_html(readiness, diag)
            if hasattr(self, "_rp_session_status"):
                self._rp_session_status.setText(diag.message)
            if hasattr(self, "_rp_readiness_status"):
                self._rp_readiness_status.setText(
                    f"{readiness.readiness_message}. Next: {readiness.next_best_action}")
            _msgs = empty_state_messages(samples, inp)
            if _msgs:
                _items = "".join(f"<li style='font-size:11px;'>{m}</li>" for m in _msgs)
                empty_html = (
                    "<p style='margin:4px 0 1px; color:#F5C542; font-size:11px;'><b>Before you rely on this</b></p>"
                    f"<ul style='margin:1px 0;'>{_items}</ul>")
        except Exception:
            readiness_html = ""

        _sep = "<hr style='border:none; border-top:1px solid #333; margin:6px 0;'>"
        # Sprint 10: a practice-bundle banner is prepended when the plan was built
        # via "Build Race Plan from This Practice". Consumed once, then cleared so a
        # subsequent plain "Build Race Strategy" doesn't show a stale banner.
        _bundle_banner = getattr(self, "_practice_bundle_banner_html", "")
        self._practice_bundle_banner_html = ""
        self._race_plan_text.setHtml(
            _bundle_banner + readiness_html + (empty_html or "") + _sep
            + render_race_plan_html(vm))

        rows = candidate_table_rows(vm)
        self._race_plan_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                self._race_plan_table.setItem(r, c, QTableWidgetItem(cell))

    def _practice_bundle_setup_linkage(self, inp: dict) -> tuple:
        """(approved_setup_id, applied_checkpoint_id, confirmed_in_gt7) for the plan.

        Reads the latest applied-in-GT7 Race checkpoint (Sprint 10 piece 2) for the
        event's car/track/layout. A checkpoint means the setup was confirmed applied
        in game at least once; its absence surfaces as a 'not confirmed' warning.
        Read-only; never raises.
        """
        try:
            if self._db is None:
                return "", "", False
            row = self._db.get_latest_applied_checkpoint(
                int(inp.get("car_id", 0) or 0), inp.get("track", "") or "",
                inp.get("layout_id", "") or "", "Race")
            if not row:
                return "", "", False
            return (str(row.get("setup_id") or ""),
                    str(row.get("checkpoint_id") or ""), True)
        except Exception:
            return "", "", False

    def _build_practice_evidence_bundle(self, inp: dict):
        """Build a PracticeEvidenceBundle from the selected practice session (pure
        engines; read-only). Returns the bundle or None on failure."""
        from strategy.race_strategy_from_session import build_strategy_evidence_from_session
        from strategy.practice_evidence_bundle import build_practice_evidence_bundle
        session_result = build_strategy_evidence_from_session(
            self._db,
            session_id=inp["session_id"], car_id=inp["car_id"],
            track=inp["track"], layout_id=inp["layout_id"],
            race_duration_minutes=inp["race_duration_minutes"],
            race_laps=inp["race_laps"],
            fuel_multiplier=inp["fuel_multiplier"],
            tyre_multiplier=inp["tyre_multiplier"],
            refuel_rate_lps=inp["refuel_rate_lps"],
            pit_loss_seconds=inp["pit_loss_seconds"],
            starting_fuel_pct=inp["starting_fuel_pct"],
            available_compounds=inp["available_compounds"],
            required_compounds=inp["required_compounds"],
            mandatory_pit_stops=inp["mandatory_pit_stops"],
        )
        approved_setup_id, checkpoint_id, confirmed = self._practice_bundle_setup_linkage(inp)
        return build_practice_evidence_bundle(
            session_result=session_result,
            car_id=inp["car_id"], car_name=inp.get("car_name", ""),
            approved_setup_id=approved_setup_id, applied_checkpoint_id=checkpoint_id,
            setup_confirmed_in_gt7=confirmed,
            session_ids=(int(inp.get("session_id", 0) or 0),),
        )

    def _practice_bundle_banner_html_for(self, bundle, inp: dict) -> str:
        """Render the practice-bundle hand-off banner: readiness, confidence,
        setup-confirmed state, missing evidence, and staleness. Pure string build."""
        from strategy.practice_evidence_bundle import detect_bundle_staleness, staleness_text
        ready = bool(getattr(bundle, "is_ready_for_strategy", False))
        confirmed = bool(getattr(bundle, "setup_confirmed_in_gt7", False))
        _stale, _reasons = detect_bundle_staleness(
            bundle,
            current_track=inp.get("track"), current_layout_id=inp.get("layout_id"),
            current_race_laps=inp.get("race_laps"),
            current_race_duration_minutes=inp.get("race_duration_minutes"),
            current_fuel_multiplier=inp.get("fuel_multiplier"),
            current_tyre_multiplier=inp.get("tyre_multiplier"),
            current_refuel_rate_lps=inp.get("refuel_rate_lps"),
        )
        if ready and confirmed and not _stale:
            border, text = "#3FA07A", "#7FD0AC"
            head = "&#10003; Race plan built from this practice"
        elif ready:
            border, text = "#C8A020", "#E6C34A"
            head = "&#9888; Race plan built from this practice — check the notes"
        else:
            border, text = "#E05050", "#E08080"
            head = "&#9940; Not enough measured evidence for a confident plan"

        notes = []
        notes.append(f"Evidence confidence: <b>{getattr(bundle, 'confidence', 'none')}</b>")
        notes.append("Setup confirmed applied in GT7"
                     if confirmed else
                     "Setup NOT confirmed applied in GT7 — press “Changes Applied in "
                     "Game” in Setup Builder so the plan matches the car.")
        for m in getattr(bundle, "missing_evidence", ()) or ():
            notes.append(f"Missing: {m}")
        for t in staleness_text(_reasons):
            notes.append(f"Stale: {t}")
        body = "".join(f"<li style='margin:1px 0;'>{n}</li>" for n in notes)
        return (
            f"<div style='background:#0E1622; border-left:4px solid {border}; "
            f"border-radius:5px; padding:8px 12px; margin-bottom:6px;'>"
            f"<div style='color:{text}; font-weight:bold; font-size:12px;'>{head}</div>"
            f"<ul style='margin:4px 0 0 0; padding-left:16px; color:#BBB; "
            f"font-size:11px;'>{body}</ul></div>")

    def _run_race_plan_from_practice(self) -> None:
        """Build a PracticeEvidenceBundle from the selected session, then plan from
        it (Sprint 10). Read-only: never applies a setup, never calls a pit."""
        try:
            inp = self._assemble_race_plan_inputs()
        except Exception as exc:
            self._race_plan_text.setHtml(
                f"<p style='color:#E8A9A3;'>Could not read race settings: {exc}</p>")
            return
        try:
            bundle = self._build_practice_evidence_bundle(inp)
        except Exception as exc:
            self._race_plan_text.setHtml(
                f"<p style='color:#E8A9A3;'>Could not bundle this practice: {exc}</p>")
            return
        self._practice_bundle = bundle
        self._race_plan_built = bool(getattr(bundle, "is_ready_for_strategy", False))
        try:
            self._practice_bundle_banner_html = self._practice_bundle_banner_html_for(bundle, inp)
        except Exception:
            self._practice_bundle_banner_html = ""
        # Reuse the deterministic plan path; it prepends the banner set above.
        self._run_race_plan()
