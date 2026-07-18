"""Event Planner tab — mixin for MainWindow (decomposition slice 4).

Extracted from ui/dashboard.py: the Event Planner tab builder and its event-list
CRUD/selection handlers (create/duplicate/delete/save/select/set-active). These
do NOT touch config["strategy"]; the four governance-pinned writers that do
(_fanout_event_to_strategy, _save_race_params, _update_race_config,
_on_garage_select_for_event) deliberately STAY on MainWindow in dashboard.py so
the frozen fan-out allowlist remains exact — the mixin calls them via the MRO.
Does not import ui.dashboard (acyclic).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt  # noqa: F401
from PyQt6.QtWidgets import (  # noqa: F401
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QCheckBox, QComboBox, QSpinBox, QLineEdit, QTextEdit,
    QListWidget, QScrollArea, QAbstractItemView,
)

from ui.gt7_data import GT7_TRACKS  # noqa: F401 — used by _build_event_planner_tab

# Module-level display constants — sourced from the NGR design system for theme
# consistency (ui/ngr_theme.py) instead of ad-hoc hex.
from ui import ngr_theme as _ngr
_DARK_CARD = _ngr.CARBON_RAISED   # was "#2A2A2A"
_TEXT = _ngr.TEXT                 # was "#E0E0E0"


class EventPlannerMixin:
    """Event Planner tab construction + event-list CRUD for MainWindow."""

    def _build_event_planner_tab(self) -> QWidget:
        widget = QWidget()
        outer_layout = QVBoxLayout(widget)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(6)
        outer_layout.addWidget(self._tab_intro_header(
            "Event Planner",
            "Create a profile for each race — track, car, format, tyres, fuel. "
            "This is the workflow's starting point. Next: fill the fields and "
            "click Set as Active; every other tab fills in from here."))
        main_layout = QHBoxLayout()
        main_layout.setSpacing(8)
        outer_layout.addLayout(main_layout, 1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(6)

        events_group = QGroupBox("Event Profiles")
        events_group.setStyleSheet(self._group_style())
        events_layout = QVBoxLayout(events_group)
        self._event_list = QListWidget()
        self._event_list.setStyleSheet(
            f"QListWidget {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; }}"
            "QListWidget::item:selected { background: #2A4A6A; }"
        )
        events_layout.addWidget(self._event_list)

        evt_btn_row = QHBoxLayout()
        for label, slot in [("+ New", self._on_event_new), ("Duplicate", self._on_event_duplicate), ("Delete", self._on_event_delete)]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "QPushButton { background: #2A2A2A; color: white; border-radius: 3px; padding: 4px 8px; }"
                "QPushButton:hover { background: #3A3A3A; }"
            )
            btn.clicked.connect(slot)
            evt_btn_row.addWidget(btn)
        events_layout.addLayout(evt_btn_row)
        left_layout.addWidget(events_group)
        left_layout.addStretch()

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setSpacing(8)

        editor_group = QGroupBox("Event Editor")
        editor_group.setStyleSheet(self._group_style())
        form = QFormLayout(editor_group)
        form.setSpacing(8)

        lbl_s = f"color: {_TEXT};"
        line_s = f"QLineEdit {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; border-radius: 3px; padding: 3px 6px; }}"
        spin_s = f"QSpinBox {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; border-radius: 3px; padding: 2px 6px; }}"
        combo_s = (
            f"QComboBox {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; border-radius: 3px; padding: 2px 6px; }}"
            f"QComboBox QAbstractItemView {{ background: {_DARK_CARD}; color: {_TEXT}; }}"
        )

        self._evt_name = QLineEdit()
        self._evt_name.setStyleSheet(line_s)
        form.addRow(QLabel("Name:", styleSheet=lbl_s), self._evt_name)

        self._evt_track = QComboBox()
        self._evt_track.setEditable(True)
        self._evt_track.setStyleSheet(combo_s)
        self._evt_track.addItem("")
        for _t in GT7_TRACKS:
            self._evt_track.addItem(_t)
        form.addRow(QLabel("Track:", styleSheet=lbl_s), self._evt_track)

        self._evt_race_type = QComboBox()
        self._evt_race_type.addItems(["Lap Race", "Timed Race"])
        self._evt_race_type.setStyleSheet(combo_s)
        form.addRow(QLabel("Race Type:", styleSheet=lbl_s), self._evt_race_type)

        self._evt_laps = QSpinBox()
        self._evt_laps.setRange(1, 500)
        self._evt_laps.setStyleSheet(spin_s)
        form.addRow(QLabel("Laps:", styleSheet=lbl_s), self._evt_laps)

        self._evt_duration = QSpinBox()
        self._evt_duration.setRange(1, 600)
        self._evt_duration.setStyleSheet(spin_s)
        form.addRow(QLabel("Duration (min):", styleSheet=lbl_s), self._evt_duration)

        def _on_race_type_changed(text: str) -> None:
            is_timed = "timed" in text.lower()
            self._evt_laps.setEnabled(not is_timed)
            self._evt_duration.setEnabled(is_timed)
        self._evt_race_type.currentTextChanged.connect(_on_race_type_changed)
        _on_race_type_changed(self._evt_race_type.currentText())

        self._evt_tyre_wear = QSpinBox()
        self._evt_tyre_wear.setRange(1, 20)
        self._evt_tyre_wear.setValue(1)
        self._evt_tyre_wear.setStyleSheet(spin_s)
        form.addRow(QLabel("Tyre Wear ×:", styleSheet=lbl_s), self._evt_tyre_wear)

        self._evt_fuel_mult = QSpinBox()
        self._evt_fuel_mult.setRange(1, 10)
        self._evt_fuel_mult.setValue(1)
        self._evt_fuel_mult.setStyleSheet(spin_s)
        form.addRow(QLabel("Fuel Multiplier ×:", styleSheet=lbl_s), self._evt_fuel_mult)

        self._evt_mand_pits = QSpinBox()
        self._evt_mand_pits.setRange(0, 5)
        self._evt_mand_pits.setStyleSheet(spin_s)
        form.addRow(QLabel("Mandatory Pits:", styleSheet=lbl_s), self._evt_mand_pits)

        self._evt_bop = QCheckBox("BoP enabled")
        self._evt_bop.setStyleSheet(f"color: {_TEXT};")
        form.addRow(QLabel("BoP:", styleSheet=lbl_s), self._evt_bop)

        self._evt_tuning = QCheckBox("Tuning allowed")
        self._evt_tuning.setStyleSheet(f"color: {_TEXT};")
        form.addRow(QLabel("Tuning:", styleSheet=lbl_s), self._evt_tuning)

        self._evt_abs = QCheckBox("ABS allowed")
        self._evt_abs.setChecked(True)
        self._evt_abs.setStyleSheet(f"color: {_TEXT};")
        form.addRow(QLabel("ABS:", styleSheet=lbl_s), self._evt_abs)

        self._tuning_perms_group = QGroupBox("Tuning Permissions")
        self._tuning_perms_group.setStyleSheet(
            f"QGroupBox {{ color: {_TEXT}; border: 1px solid #444; margin-top: 8px; padding-top: 8px; }}"
            f"QGroupBox::title {{ color: #AAE4AA; }}"
        )
        _tp_layout = QVBoxLayout(self._tuning_perms_group)
        _tp_layout.addWidget(
            QLabel("Which setup areas are allowed to be modified?",
                   styleSheet="color: #999; font-size: 11px;")
        )
        self._tuning_cat_checks: dict[str, QCheckBox] = {}
        for _tcode, _tdesc in self._TUNING_CATEGORIES:
            _cb = QCheckBox(_tdesc)
            _cb.setStyleSheet(f"color: {_TEXT}; font-size: 11px;")
            self._tuning_cat_checks[_tcode] = _cb
            _tp_layout.addWidget(_cb)
        self._tuning_perms_group.hide()
        form.addRow("", self._tuning_perms_group)

        def _update_tuning_perms_visibility() -> None:
            show = self._evt_tuning.isChecked()
            if hasattr(self, "_tuning_perms_group"):
                self._tuning_perms_group.setVisible(show)
        self._evt_bop.toggled.connect(lambda _: _update_tuning_perms_visibility())
        self._evt_tuning.toggled.connect(lambda _: _update_tuning_perms_visibility())
        _update_tuning_perms_visibility()

        self._evt_weather = QComboBox()
        self._evt_weather.addItems(["Fixed Dry", "Fixed Wet", "Random", "Wet Risk"])
        self._evt_weather.setStyleSheet(combo_s)
        form.addRow(QLabel("Weather:", styleSheet=lbl_s), self._evt_weather)

        self._evt_damage = QComboBox()
        self._evt_damage.addItems(["None", "Light", "Heavy"])
        self._evt_damage.setStyleSheet(combo_s)
        form.addRow(QLabel("Damage:", styleSheet=lbl_s), self._evt_damage)

        self._evt_refuel_rate = QSpinBox()
        self._evt_refuel_rate.setRange(1, 100)
        self._evt_refuel_rate.setSuffix(" L/s")
        self._evt_refuel_rate.setValue(10)
        self._evt_refuel_rate.setStyleSheet(spin_s)
        self._evt_refuel_rate.setToolTip("Fuel added per second during a pit stop (used by Strategy Builder)")
        form.addRow(QLabel("Refuel Rate:", styleSheet=lbl_s), self._evt_refuel_rate)

        from data.tyres import ALL_COMPOUNDS as _ALL_CPDS
        _avail_w = QWidget()
        _avail_grid = QGridLayout(_avail_w)
        _avail_grid.setContentsMargins(0, 0, 0, 0)
        _avail_grid.setSpacing(4)
        self._avail_tyre_checks: dict[str, QCheckBox] = {}
        _avail_cols = 3
        for _ci, _tc in enumerate(_ALL_CPDS):
            _cb = QCheckBox(_tc.name)
            _cb.setStyleSheet(f"color: {_TEXT}; font-size: 11px;")
            self._avail_tyre_checks[_tc.code] = _cb
            _avail_grid.addWidget(_cb, _ci // _avail_cols, _ci % _avail_cols)
        form.addRow(QLabel("Available Tyres:", styleSheet=lbl_s), _avail_w)

        _req_w = QWidget()
        _req_grid = QGridLayout(_req_w)
        _req_grid.setContentsMargins(0, 0, 0, 0)
        _req_grid.setSpacing(4)
        self._req_tyre_checks: dict[str, QCheckBox] = {}
        for _ci, _tc in enumerate(_ALL_CPDS):
            _cb = QCheckBox(_tc.name)
            _cb.setStyleSheet(f"color: {_TEXT}; font-size: 11px;")
            _cb.setEnabled(False)
            self._req_tyre_checks[_tc.code] = _cb
            _req_grid.addWidget(_cb, _ci // 3, _ci % 3)
        form.addRow(QLabel("Required Tyres:", styleSheet=lbl_s), _req_w)

        def _avail_toggled(code: str, checked: bool) -> None:
            req_cb = self._req_tyre_checks.get(code)
            if req_cb:
                if not checked:
                    req_cb.setChecked(False)
                req_cb.setEnabled(checked)
        for _code, _cb in self._avail_tyre_checks.items():
            _cb.toggled.connect(lambda c, _code=_code: _avail_toggled(_code, c))

        self._evt_notes = QTextEdit()
        self._evt_notes.setMaximumHeight(80)
        self._evt_notes.setStyleSheet(
            f"QTextEdit {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; border-radius: 3px; padding: 4px; }}"
        )
        form.addRow(QLabel("Notes:", styleSheet=lbl_s), self._evt_notes)

        save_btn_row = QHBoxLayout()
        from ui import ngr_theme as _ngr_ev
        btn_save_evt = QPushButton("Save Event")
        btn_save_evt.setStyleSheet(_ngr_ev.secondary_button_qss())
        btn_save_evt.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save_evt.clicked.connect(self._on_event_save)
        btn_set_active = QPushButton("Set as Active")
        btn_set_active.setStyleSheet(_ngr_ev.primary_button_qss())
        btn_set_active.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_set_active.clicked.connect(self._on_event_set_active)
        save_btn_row.addStretch()
        save_btn_row.addWidget(btn_save_evt)
        save_btn_row.addWidget(btn_set_active)
        form.addRow("", save_btn_row)

        right_layout.addWidget(editor_group)
        right_layout.addStretch()
        right_scroll.setWidget(right_container)

        main_layout.addWidget(left_widget, 1)
        main_layout.addWidget(right_scroll, 3)

        self._event_list.currentRowChanged.connect(self._on_event_selected)
        self._refresh_event_list()
        return widget

    def _refresh_event_list(self) -> None:
        if not hasattr(self, "_event_list"):
            return
        if self._db is not None:
            db_events = self._db.get_all_events()
            if not db_events:
                # One-time migration: seed DB from config on first run
                for evt in self._config.get("events", []):
                    if evt.get("name"):
                        self._db.upsert_event(evt)
                db_events = self._db.get_all_events()
            events = db_events
        else:
            events = self._config.get("events", [])
        self._event_list.blockSignals(True)
        self._event_list.clear()
        for evt in events:
            self._event_list.addItem(evt.get("name", "Unnamed Event"))
        self._event_list.blockSignals(False)

    def _on_event_selected(self, row: int) -> None:
        if row < 0:
            return
        if self._db is not None:
            events = self._db.get_all_events()
        else:
            events = self._config.get("events", [])
        if row >= len(events):
            return
        evt = events[row]
        try:
            self._evt_name.setText(evt.get("name", ""))
            track_idx = self._evt_track.findText(evt.get("track", ""))
            if track_idx >= 0:
                self._evt_track.setCurrentIndex(track_idx)
            else:
                self._evt_track.setCurrentText(evt.get("track", ""))
            self._evt_race_type.setCurrentIndex(max(0, self._evt_race_type.findText(evt.get("race_type", "Lap Race"))))
            self._evt_laps.setValue(evt.get("laps", 1))
            # Support both DB key (duration_mins) and legacy config key (duration)
            self._evt_duration.setValue(evt.get("duration_mins", evt.get("duration", 1)))
            # QSpinBox.setValue requires int; DB REAL columns return float — cast explicitly.
            self._evt_tyre_wear.setValue(int(round(evt.get("tyre_wear", 1) or 1)))
            self._evt_fuel_mult.setValue(int(round(evt.get("fuel_mult", 1) or 1)))
            # Support both DB key (mandatory_stops) and legacy config key (mand_pits)
            self._evt_mand_pits.setValue(int(evt.get("mandatory_stops", evt.get("mand_pits", 0)) or 0))
            self._evt_bop.setChecked(bool(evt.get("bop", False)))
            self._evt_tuning.setChecked(bool(evt.get("tuning", False)))
            self._evt_abs.setChecked(bool(evt.get("abs", True)))
            self._evt_weather.setCurrentIndex(max(0, self._evt_weather.findText(evt.get("weather", "Fixed Dry"))))
            self._evt_damage.setCurrentIndex(max(0, self._evt_damage.findText(evt.get("damage", "None"))))
            if hasattr(self, "_evt_refuel_rate"):
                # Support both DB key (refuel_rate_lps) and legacy config key (refuel_rate)
                self._evt_refuel_rate.setValue(int(round(evt.get("refuel_rate_lps", evt.get("refuel_rate", 10)) or 10)))
            if hasattr(self, "_avail_tyre_checks"):
                from data.tyres import normalise_code as _nc
                _at = evt.get("avail_tyres", [])
                if isinstance(_at, str):
                    _at = [_nc(c.strip()) for c in _at.split(",") if c.strip()]
                    _at = [c for c in _at if c]
                for _code, _cb in self._avail_tyre_checks.items():
                    _cb.setChecked(_code in _at)
            if hasattr(self, "_req_tyre_checks"):
                from data.tyres import normalise_code as _nc2
                _rt = evt.get("req_tyres", [])
                if isinstance(_rt, str):
                    _code = _nc2(_rt.strip())
                    _rt = [_code] if _code else []
                _avail = {code for code, cb in self._avail_tyre_checks.items() if cb.isChecked()}
                for _code, _cb in self._req_tyre_checks.items():
                    _cb.setEnabled(_code in _avail)
                    _cb.setChecked(_code in _rt and _code in _avail)
            if hasattr(self, "_tuning_cat_checks"):
                _atc = evt.get("allowed_tuning_categories", [])
                for _tcode, _cb in self._tuning_cat_checks.items():
                    _cb.setChecked(_tcode in _atc)
                _tun_on = evt.get("tuning", False)
                self._tuning_perms_group.setVisible(bool(_tun_on))
            self._evt_notes.setPlainText(evt.get("notes", ""))
        except Exception:
            import traceback
            traceback.print_exc()

    def _on_event_new(self) -> None:
        try:
            self._evt_name.clear()
            self._evt_notes.clear()
            self._evt_track.setCurrentIndex(0)
            self._evt_race_type.setCurrentIndex(0)
            self._evt_laps.setValue(1)
            self._evt_duration.setValue(1)
            self._evt_tyre_wear.setValue(1)
            self._evt_fuel_mult.setValue(1)
            self._evt_mand_pits.setValue(0)
            self._evt_bop.setChecked(False)
            self._evt_tuning.setChecked(False)
            self._evt_abs.setChecked(True)
            self._evt_weather.setCurrentIndex(0)
            self._evt_damage.setCurrentIndex(0)
            if hasattr(self, "_evt_refuel_rate"):
                self._evt_refuel_rate.setValue(10)
            if hasattr(self, "_avail_tyre_checks"):
                for _cb in self._avail_tyre_checks.values():
                    _cb.setChecked(False)
            if hasattr(self, "_req_tyre_checks"):
                for _cb in self._req_tyre_checks.values():
                    _cb.setChecked(False)
                    _cb.setEnabled(False)
            if hasattr(self, "_tuning_cat_checks"):
                for _cb in self._tuning_cat_checks.values():
                    _cb.setChecked(False)
                if hasattr(self, "_tuning_perms_group"):
                    self._tuning_perms_group.hide()
            self._event_list.clearSelection()
            self._evt_name.setFocus()
        except Exception:
            pass

    def _on_event_duplicate(self) -> None:
        try:
            row = self._event_list.currentRow()
            if row < 0:
                return
            if self._db is not None:
                events = self._db.get_all_events()
            else:
                events = self._config.get("events", [])
            if row >= len(events):
                return
            dup = copy.deepcopy(events[row])
            dup["name"] = dup.get("name", "Event") + " Copy"
            if self._db is not None:
                self._db.upsert_event(dup)
            cfg_events = self._config.setdefault("events", [])
            cfg_events.append(dup)
            self._persist_config()
            self._refresh_event_list()
            self._event_list.setCurrentRow(self._event_list.count() - 1)
        except Exception:
            pass

    def _on_event_delete(self) -> None:
        try:
            row = self._event_list.currentRow()
            if row < 0:
                return
            if self._db is not None:
                events = self._db.get_all_events()
            else:
                events = self._config.get("events", [])
            if row >= len(events):
                return
            name = events[row].get("name", "")
            if self._db is not None and name:
                self._db.delete_event(name)
            cfg_events = self._config.get("events", [])
            self._config["events"] = [e for e in cfg_events if e.get("name") != name]
            self._persist_config()
            self._refresh_event_list()
        except Exception:
            pass

    def _on_event_save(self) -> None:
        try:
            name = self._evt_name.text().strip()
            if not name:
                return
            evt = {
                "name":                      name,
                "track":                     self._evt_track.currentText(),
                "race_type":                 self._evt_race_type.currentText(),
                "laps":                      self._evt_laps.value(),
                "duration_mins":             self._evt_duration.value(),
                "tyre_wear":                 self._evt_tyre_wear.value(),
                "fuel_mult":                 self._evt_fuel_mult.value(),
                "mandatory_stops":           self._evt_mand_pits.value(),
                "bop":                       self._evt_bop.isChecked(),
                "tuning":                    self._evt_tuning.isChecked(),
                "abs":                       self._evt_abs.isChecked(),
                "weather":                   self._evt_weather.currentText(),
                "damage":                    self._evt_damage.currentText(),
                "refuel_rate_lps":           self._evt_refuel_rate.value() if hasattr(self, "_evt_refuel_rate") else 10,
                "avail_tyres":               [code for code, cb in self._avail_tyre_checks.items() if cb.isChecked()] if hasattr(self, "_avail_tyre_checks") else [],
                "req_tyres":                 [code for code, cb in self._req_tyre_checks.items() if cb.isChecked()] if hasattr(self, "_req_tyre_checks") else [],
                "allowed_tuning_categories": [code for code, cb in self._tuning_cat_checks.items() if cb.isChecked()] if hasattr(self, "_tuning_cat_checks") else [],
                "notes":                     self._evt_notes.toPlainText().strip(),
            }
            # DB is the authoritative store
            if self._db is not None:
                self._db.upsert_event(evt)
            # Keep config in sync during transition period
            cfg_events = self._config.setdefault("events", [])
            for i, e in enumerate(cfg_events):
                if e.get("name") == name:
                    cfg_events[i] = evt
                    break
            else:
                cfg_events.append(evt)
            # Legacy Fan-Out Removal Phase 4: if the saved event IS the active
            # event, re-sync the legacy config["strategy"] fan-out from the same
            # widgets, so the DB record and the fan-out can no longer diverge
            # (readers are already DB-first since Phases 2-3; this keeps the
            # remaining fan-out readers fresh too). Config-dict only — the
            # activation side effects (tracker race config, advisor context,
            # tab syncs) remain exclusive to "Set as Active".
            if name == self._config.get("active_event_id"):
                self._fanout_event_to_strategy(name)
                # Phase 6a: the active event's rules (incl. event_id/track)
                # changed — keep the dispatcher's session tag fresh too.
                self._push_session_tag()
            self._persist_config()
            self._refresh_event_list()
            for i in range(self._event_list.count()):
                if self._event_list.item(i).text() == name:
                    self._event_list.setCurrentRow(i)
                    break
        except Exception:
            pass

    def _on_event_set_active(self) -> None:
        try:
            self._on_event_save()
            evt_name = self._evt_name.text().strip()
            if not evt_name:
                return
            self._config["active_event_id"] = evt_name

            # Phase 4: the fan-out block lives in _fanout_event_to_strategy so
            # the save path can re-sync it; activation keeps all its side
            # effects (tracker push, advisor context, syncs) below.
            strat = self._fanout_event_to_strategy(evt_name)

            if self._tracker is not None:
                from telemetry.state import RaceType
                type_map = {"lap": RaceType.LAP, "timed": RaceType.TIMED}
                self._tracker.set_race_config(
                    type_map.get(strat["race_type"], RaceType.UNKNOWN),
                    strat["race_duration_minutes"] if strat["race_type"] == "timed" else 0.0,
                )
            self._persist_config()
            self._bridge.event_log_entry.emit(f"Active event set: {evt_name}")
            # Push event context to driving advisor so AI prompts have full event
            # details. Rule-Cache Deletion: the strategy dict no longer carries
            # the rules, so the no-DB fallback goes through _active_event()
            # (which reads the config["events"] mirror — full rules).
            if hasattr(self, "_driving_advisor") and self._driving_advisor is not None:
                _evt_full = self._db.get_event(evt_name) if self._db is not None else {}
                self._driving_advisor.set_event_context(
                    _evt_full or self._active_event() or strat)
            # Group 62: push ABS regulation into the strategy engine so it can
            # apply no-ABS driving advice from the moment the event is activated.
            if getattr(self, "_strategy_engine", None) is not None:
                _ae = self._db.get_event(evt_name) if self._db is not None else {}
                _ae = _ae or self._active_event() or strat
                self._strategy_engine.set_abs_allowed(bool(_ae.get("abs", True)))
            # Rule-Cache Deletion: the explicit _apply_setup_permissions call
            # that followed this sync was REDUNDANT since Phase 3 — the sync
            # itself applies permissions from the just-saved DB event
            # (EventContext, identical values) — and its bop/tuning/categories
            # inputs are no longer cached in the strategy dict. Deleted.
            self._sync_setup_builder_from_event()
            self._sync_strategy_from_event()
            if self._query_listener is not None:
                _ql_name, _ql_specs = self._load_car_specs_for_current()
                self._query_listener.update_car_specs(_ql_specs)
            # Reset stale fuel-burn label when switching events with no live/loaded data
            if hasattr(self, "_lbl_fuel_burn_display"):
                _fb_avg = getattr(self._tracker, "avg_fuel_per_lap", 0) if self._tracker else 0
                _fb_loaded = getattr(self, "_loaded_session_avg_fuel", 0.0) or 0.0
                if _fb_avg <= 0 and _fb_loaded <= 0:
                    self._lbl_fuel_burn_display.setText("— (complete practice laps to calibrate)")
            # Refresh saved plans combo for the newly active event
            self._sb_refresh_saved_plans_combo()
            # Home Dashboard: keep an open Home tab current after the active
            # event changes (display-only; no-op when Home is not visible).
            self._home_refresh_if_visible()
        except Exception:
            import traceback; traceback.print_exc()
