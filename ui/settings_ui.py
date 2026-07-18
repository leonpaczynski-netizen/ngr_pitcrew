"""Settings tab — mixin for MainWindow (decomposition slice 2).

Extracted verbatim from ui/dashboard.py: the Settings tab builder plus its
save/reset, voice-picker/download, and PTT/mic handlers. Every method still
operates on the shared MainWindow ``self`` (config, announcer, query_listener,
bridge, and the shared _make_slider/_make_dspin/_group_style helpers resolve
via the MRO), so behaviour is unchanged — this only moves ~490 lines out of
the 8.9k-line monolith. No import of ui.dashboard (keeps the base-class import
in dashboard.py acyclic).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer  # noqa: F401
from PyQt6.QtWidgets import (  # noqa: F401
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QPushButton, QCheckBox, QComboBox, QSlider, QSpinBox, QDoubleSpinBox,
    QLineEdit, QTextEdit, QScrollArea, QMessageBox, QInputDialog,
)

# Module-level display constant — must match dashboard.py
_TEXT = "#E0E0E0"


class SettingsMixin:
    """Settings tab construction + handlers for MainWindow."""

    def _build_settings_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(12)
        layout.setContentsMargins(10, 10, 10, 10)

        # Game Data
        data_box = QGroupBox("Game Data")
        data_box.setStyleSheet(self._group_style())
        data_box.setToolTip(
            "Fetch latest cars, tracks and BOP data from the web.\n"
            "Sources: gran-turismo.com (cars/tracks) · dg-edge.com (BOP)"
        )
        data_vlay = QVBoxLayout(data_box)
        data_btn_row = QHBoxLayout()
        self._btn_refresh_web = QPushButton("Refresh Data from Web")
        self._btn_refresh_web.setFixedHeight(28)
        self._btn_refresh_web.setToolTip(
            "Downloads the latest car list, track list, and BOP settings from:\n"
            "  • gran-turismo.com/gb/gt7/carlist\n"
            "  • gran-turismo.com/sg/gt7/tracklist\n"
            "  • dg-edge.com/database/bop\n"
            "Needs an internet connection; the status line below reports progress."
        )
        self._btn_refresh_web.clicked.connect(self._refresh_data_from_web)
        self._btn_open_extra = QPushButton("Edit Extra JSON")
        self._btn_open_extra.setFixedHeight(28)
        self._btn_open_extra.setToolTip(
            "Open data/gt7_extra.json to manually add cars or tracks\n"
            "that couldn't be scraped automatically."
        )
        self._btn_open_extra.clicked.connect(self._open_extra_json)
        data_btn_row.addWidget(self._btn_refresh_web)
        data_btn_row.addWidget(self._btn_open_extra)
        data_vlay.addLayout(data_btn_row)
        self._lbl_reload_status = QLabel("", wordWrap=True)
        self._lbl_reload_status.setStyleSheet("color: #88CCFF; font-size: 11px;")
        data_vlay.addWidget(self._lbl_reload_status)
        layout.addWidget(data_box)

        # Connection
        conn_box = QGroupBox("Connection")
        conn_box.setStyleSheet(self._group_style())
        conn_form = QFormLayout(conn_box)
        self._edit_host = QLineEdit(self._config.get("connection", {}).get("host", "127.0.0.1"))
        self._spin_port = QSpinBox()
        self._spin_port.setRange(1024, 65535)
        self._spin_port.setValue(self._config.get("connection", {}).get("port", 33741))
        conn_form.addRow("Host:", self._edit_host)
        conn_form.addRow("Port:", self._spin_port)
        layout.addWidget(conn_box)

        # Voice
        voice_box = QGroupBox("Voice Alerts")
        voice_box.setStyleSheet(self._group_style())
        voice_layout = QFormLayout(voice_box)
        vc = self._config.get("voice", {})

        self._chk_voice_enabled  = QCheckBox(); self._chk_voice_enabled.setChecked(vc.get("enabled", True))
        self._chk_tyre_alerts    = QCheckBox(); self._chk_tyre_alerts.setChecked(vc.get("tyre_alerts", True))
        self._chk_lap_alerts     = QCheckBox(); self._chk_lap_alerts.setChecked(vc.get("lap_alerts", True))
        self._chk_pos_alerts     = QCheckBox(); self._chk_pos_alerts.setChecked(vc.get("position_alerts", False))
        self._chk_fuel_alerts    = QCheckBox(); self._chk_fuel_alerts.setChecked(vc.get("fuel_alerts", True))
        self._chk_countdown      = QCheckBox(); self._chk_countdown.setChecked(vc.get("countdown_alerts", False))

        self._slider_rate, rate_row = self._make_slider(100, 250, vc.get("rate", 175), "wpm")
        self._slider_volume, vol_row = self._make_slider(0, 100, int(vc.get("volume", 1.0) * 100), "%")

        self._combo_voice = QComboBox()
        self._populate_voices()

        voice_layout.addRow("Enabled:",         self._chk_voice_enabled)
        voice_layout.addRow("Speech rate:",      rate_row)
        voice_layout.addRow("Volume:",           vol_row)
        voice_layout.addRow("Voice:",            self._combo_voice)
        voice_layout.addRow("Tyre alerts:",      self._chk_tyre_alerts)
        voice_layout.addRow("Lap alerts:",       self._chk_lap_alerts)
        voice_layout.addRow("Position alerts:",  self._chk_pos_alerts)
        voice_layout.addRow("Fuel/pit alerts:",  self._chk_fuel_alerts)
        voice_layout.addRow("Lap countdown:",    self._chk_countdown)

        voice_btn_row = QHBoxLayout()
        btn_test = QPushButton("Test Voice")
        btn_test.setToolTip("Speak a test line using the currently saved voice.")
        btn_test.clicked.connect(self._announcer.test_voice)
        self._btn_download_voice = QPushButton("Download voice…")
        self._btn_download_voice.setToolTip(
            "Download an additional natural (Piper) voice — runs fully offline "
            "afterwards. Pick from the list; it appears in Voice once installed.")
        self._btn_download_voice.clicked.connect(self._on_download_piper_voice)
        voice_btn_row.addWidget(btn_test)
        voice_btn_row.addWidget(self._btn_download_voice)
        voice_btn_row.addStretch()
        voice_layout.addRow("", voice_btn_row)
        layout.addWidget(voice_box)

        # Fuel config
        fuel_box = QGroupBox("Fuel")
        fuel_box.setStyleSheet(self._group_style())
        fuel_form = QFormLayout(fuel_box)
        fc = self._config.get("fuel", {})
        self._spin_safety   = self._make_dspin(fc.get("safety_margin_laps", 1.0), 0.0, 5.0)
        self._spin_pit_thr  = self._make_dspin(fc.get("pit_threshold_liters", 0.5), 0.1, 10.0)
        fuel_form.addRow("Safety margin (laps):", self._spin_safety)
        fuel_form.addRow("Pit detect threshold (L):", self._spin_pit_thr)
        layout.addWidget(fuel_box)

        # Voice Queries (Push-to-Talk)
        ptt_box = QGroupBox("Voice Queries (Push-to-Talk)")
        ptt_box.setStyleSheet(self._group_style())
        ptt_form = QFormLayout(ptt_box)
        qb = self._config.get("query_button", {})
        qc = self._config.get("query", {})

        self._ptt_status_lbl = QLabel("RADIO READY")
        self._ptt_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ptt_status_lbl.setStyleSheet(
            "color: #2EA043; background: #0D1B10; border: 1px solid #2EA043; "
            "border-radius: 3px; padding: 3px 10px; font-size: 11px; font-weight: bold; "
            "letter-spacing: 1px;"
        )
        ptt_form.addRow("", self._ptt_status_lbl)
        self._bridge.ptt_status.connect(self._on_ptt_status)

        self._ptt_binding_lbl = QLabel(self._format_binding(qb))
        self._ptt_binding_lbl.setStyleSheet("color: #AAE4AA;")
        ptt_detect_btn = QPushButton("Detect Button...")
        ptt_detect_btn.setToolTip(
            "Listen for a keyboard key, controller or wheel button to bind as\n"
            "push-to-talk. You'll confirm before an existing binding is replaced."
        )
        ptt_detect_btn.clicked.connect(self._on_detect_ptt_button)
        ptt_clear_btn = QPushButton("Clear")
        ptt_clear_btn.setToolTip("Remove the current push-to-talk button assignment.")
        ptt_clear_btn.clicked.connect(self._on_clear_ptt_binding)
        detect_row_w = QWidget()
        detect_row_l = QHBoxLayout(detect_row_w)
        detect_row_l.setContentsMargins(0, 0, 0, 0)
        detect_row_l.addWidget(ptt_detect_btn)
        detect_row_l.addWidget(ptt_clear_btn)
        detect_row_l.addWidget(self._ptt_binding_lbl)
        detect_row_l.addStretch()
        ptt_form.addRow("Push-to-talk button:", detect_row_w)

        # Local-only recognition (Sprint 11): speech never leaves the machine.
        # The cloud option was removed — Pit Crew is fully local and private.
        self._combo_speech_backend = QComboBox()
        self._combo_speech_backend.addItem("Local — CMU PocketSphinx (offline)", "sphinx")
        self._combo_speech_backend.setCurrentIndex(0)
        self._combo_speech_backend.setEnabled(False)
        self._combo_speech_backend.setToolTip(
            "Speech is recognised locally (offline) — it never leaves your PC.")
        ptt_form.addRow("Speech recognition:", self._combo_speech_backend)

        self._combo_microphone = QComboBox()
        self._combo_microphone.addItem("System default", None)
        self._populate_microphones()
        cur_mic = qc.get("mic_index", None)
        for i in range(self._combo_microphone.count()):
            if self._combo_microphone.itemData(i) == cur_mic:
                self._combo_microphone.setCurrentIndex(i)
                break
        btn_test_mic = QPushButton("Test Mic (1 s)")
        self._btn_find_mic = QPushButton("Find Mic")
        self._btn_find_mic.setToolTip(
            "Scan all input devices and auto-select the one producing audio"
        )
        self._lbl_mic_rms = QLabel("—")
        self._lbl_mic_rms.setStyleSheet("color: #AAE4AA;")
        mic_row_w = QWidget()
        mic_row_l = QHBoxLayout(mic_row_w)
        mic_row_l.setContentsMargins(0, 0, 0, 0)
        mic_row_l.addWidget(self._combo_microphone)
        mic_row_l.addWidget(btn_test_mic)
        mic_row_l.addWidget(self._btn_find_mic)
        mic_row_l.addWidget(self._lbl_mic_rms)
        ptt_form.addRow("Microphone:", mic_row_w)
        btn_test_mic.clicked.connect(self._on_test_mic)
        self._btn_find_mic.clicked.connect(self._on_find_mic)

        self._spin_record_secs = QDoubleSpinBox()
        self._spin_record_secs.setRange(1.0, 10.0)
        self._spin_record_secs.setDecimals(1)
        self._spin_record_secs.setSuffix(" s")
        self._spin_record_secs.setValue(float(qc.get("record_secs", 3.0)))
        ptt_form.addRow("Recording window:", self._spin_record_secs)

        btn_test_ptt = QPushButton("Test (simulate press)")
        btn_test_ptt.clicked.connect(self._on_test_ptt)
        ptt_form.addRow("", btn_test_ptt)

        layout.addWidget(ptt_box)

        # Driver Profile
        profile_box = QGroupBox("Driver Profile")
        profile_box.setStyleSheet(self._group_style())
        profile_layout = QVBoxLayout(profile_box)
        profile_layout.setSpacing(8)

        # Stats refresh row
        stats_row_w = QWidget()
        stats_row_l = QHBoxLayout(stats_row_w)
        stats_row_l.setContentsMargins(0, 0, 0, 0)
        self._btn_refresh_stats = QPushButton("Refresh Stats")
        self._btn_refresh_stats.setToolTip(
            "Recompute your driving statistics from all recorded sessions.\n"
            "These stats are automatically appended to every AI prompt so the\n"
            "AI always sees your current performance level."
        )
        self._lbl_profile_stats = QLabel("Click 'Refresh Stats' to generate from session history.")
        self._lbl_profile_stats.setStyleSheet("color: #AAE4AA;")
        self._lbl_profile_stats.setWordWrap(True)
        self._btn_refresh_stats.clicked.connect(self._run_refresh_stats)
        stats_row_l.addWidget(self._btn_refresh_stats)
        stats_row_l.addWidget(self._lbl_profile_stats, stretch=1)
        profile_layout.addWidget(stats_row_w)


        # Proposed profile text (hidden until a proposal arrives)
        self._profile_proposal_text = QTextEdit()
        self._profile_proposal_text.setReadOnly(True)
        self._profile_proposal_text.setMinimumHeight(220)
        self._profile_proposal_text.setPlaceholderText(
            "Proposed profile changes will appear here for review."
        )
        self._profile_proposal_text.setVisible(False)
        profile_layout.addWidget(self._profile_proposal_text)

        # Accept / Discard row (hidden until proposal arrives)
        self._profile_action_row = QWidget()
        action_l = QHBoxLayout(self._profile_action_row)
        action_l.setContentsMargins(0, 0, 0, 0)
        self._btn_apply_profile   = QPushButton("Apply Changes")
        self._btn_discard_profile = QPushButton("Discard")
        self._btn_apply_profile.setStyleSheet("background: #2a6e2a; color: white;")
        self._btn_apply_profile.clicked.connect(self._apply_profile_update)
        self._btn_discard_profile.clicked.connect(self._discard_profile_update)
        action_l.addStretch()
        action_l.addWidget(self._btn_apply_profile)
        action_l.addWidget(self._btn_discard_profile)
        self._profile_action_row.setVisible(False)
        profile_layout.addWidget(self._profile_action_row)

        layout.addWidget(profile_box)

        # Developer mode
        dev_box = QGroupBox("Developer")
        dev_box.setStyleSheet(self._group_style())
        dev_layout = QVBoxLayout(dev_box)
        self._dev_mode_check = QCheckBox("Enable Developer Mode")
        self._dev_mode_check.setChecked(self._config.get("developer_mode", False))
        self._dev_mode_check.setStyleSheet(f"color: {_TEXT};")
        self._dev_mode_check.setToolTip(
            "Shows additional diagnostic detail and raw telemetry payloads."
        )
        dev_layout.addWidget(self._dev_mode_check)
        layout.addWidget(dev_box)

        # Save / reset buttons
        btn_row = QHBoxLayout()
        btn_save  = QPushButton("Save Settings")
        btn_reset = QPushButton("Reset to Defaults")
        btn_save.clicked.connect(self._save_settings)
        btn_reset.clicked.connect(self._reset_settings)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_reset)
        layout.addLayout(btn_row)
        layout.addStretch()

        scroll.setWidget(inner)
        return scroll

    @staticmethod
    def _format_binding(qb: dict) -> str:
        if not qb:
            return "Not configured"
        btype = qb.get("type", "")
        if btype == "keyboard":
            return f"Keyboard: {qb.get('key', '?')}"
        if btype == "joystick":
            dev = qb.get("device")
            base = f"Joystick button {qb.get('button_index', '?')}"
            return f"{base} ({dev})" if dev else base
        return "Not configured"

    @staticmethod
    def _bindings_equal(a: dict, b: dict) -> bool:
        """True when two PTT bindings refer to the same physical control."""
        if not a or not b or a.get("type") != b.get("type"):
            return False
        if a.get("type") == "keyboard":
            return a.get("key") == b.get("key")
        if a.get("type") == "joystick":
            return a.get("button_index") == b.get("button_index")
        return False

    # ------------------------------------------------------------------
    # PTT detection — split into a factory + pure-ish apply step so the real
    # settings-UI path is testable without opening a blocking modal dialog.
    # ------------------------------------------------------------------

    def _make_button_detect_dialog(self):
        """Factory for the canonical PTT button-detection dialog.

        Isolated behind a method so tests can substitute a non-blocking fake and
        still exercise the real ``_on_detect_ptt_button`` code path. Production
        always returns the one canonical dialog from ``ui.button_detect_dialog``.
        """
        from ui.button_detect_dialog import ButtonDetectDialog
        return ButtonDetectDialog(self)

    def _pause_query_listener(self) -> None:
        """Stop the live PTT keyboard hook so the detect dialog sees the keypress
        first. Safe to call when no listener exists."""
        ql = getattr(self, "_query_listener", None)
        if ql is None:
            return
        pl = getattr(ql, "_pynput_listener", None)
        if pl is not None:
            try:
                pl.stop()
            except Exception:
                pass
            ql._pynput_listener = None

    def _resume_query_listener(self) -> None:
        """Restart the PTT keyboard hook with whatever binding is now current."""
        ql = getattr(self, "_query_listener", None)
        if ql is None:
            return
        try:
            ql._setup_keyboard_listener()
        except Exception as e:
            print(f"[Settings] listener restart error: {e}")

    def _show_ptt_message(self, text: str, *, title: str = "Push-to-talk") -> None:
        QMessageBox.information(self, title, text)

    def _confirm_replace_binding(self, existing: dict, new: dict) -> bool:
        reply = QMessageBox.question(
            self,
            "Replace push-to-talk binding?",
            "Replace current binding:\n"
            f"    {self._format_binding(existing)}\n\n"
            "with the newly detected:\n"
            f"    {self._format_binding(new)}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _apply_detected_ptt_binding(self, binding: dict) -> bool:
        """Persist a freshly detected binding. Returns True if it was stored.

        Warns on a duplicate (already-assigned) button and requires explicit
        confirmation before overwriting an existing binding.
        """
        if not binding:
            return False
        existing = self._config.get("query_button", {}) or {}
        if existing and self._bindings_equal(existing, binding):
            self._show_ptt_message(
                "That button is already assigned to push-to-talk.",
                title="Duplicate binding",
            )
            return False
        if existing and not self._confirm_replace_binding(existing, binding):
            return False
        self._config.setdefault("query_button", {}).clear()
        self._config["query_button"].update(binding)
        self._ptt_binding_lbl.setText(self._format_binding(binding))
        self._persist_config()
        return True

    def _on_detect_ptt_button(self) -> None:
        # Pause the live keyboard hook so it doesn't consume the keypress before
        # the detect dialog sees it; always restart it afterwards.
        self._pause_query_listener()
        try:
            dlg = self._make_button_detect_dialog()
            accepted = bool(dlg.exec())
            binding = (
                dict(dlg.detected_binding)
                if (accepted and dlg.detected_binding) else None
            )
            joystick_available = bool(getattr(dlg, "joystick_available", True))
        finally:
            self._resume_query_listener()

        if binding is None:
            # Cancelled, Escape, or timed out — never disturb the existing
            # binding. If nothing was detected and no controller was connected,
            # say so honestly rather than silently doing nothing.
            if not joystick_available:
                self._show_ptt_message(
                    "No button detected.\n\n"
                    "No controller or wheel was connected. You can bind a "
                    "keyboard key instead, or connect your device and try again.",
                    title="No button detected",
                )
            return

        self._apply_detected_ptt_binding(binding)

    def _on_clear_ptt_binding(self) -> None:
        if not (self._config.get("query_button") or {}):
            self._show_ptt_message("No push-to-talk button is currently assigned.")
            return
        reply = QMessageBox.question(
            self,
            "Clear push-to-talk binding?",
            "Remove the current push-to-talk button assignment?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._config.setdefault("query_button", {}).clear()
        self._ptt_binding_lbl.setText(self._format_binding({}))
        self._persist_config()
        # Rebind the live listener so it stops firing on the cleared key.
        self._pause_query_listener()
        self._resume_query_listener()

    def _on_test_ptt(self) -> None:
        if self._query_listener is not None:
            try:
                self._query_listener._trigger_queue.put_nowait(True)
            except Exception:
                pass

    def _on_test_mic(self) -> None:
        """Record 1 second from the selected mic and report RMS level."""
        mic_idx = self._combo_microphone.currentData()
        self._lbl_mic_rms.setText("recording…")
        self._lbl_mic_rms.setStyleSheet("color: #F5C542;")

        def _run():
            try:
                from voice.query_listener import _record_audio
                ret = _record_audio(1.0, mic_idx)
                if ret is None:
                    result, colour = "mic error — check privacy settings", "#C0392B"
                else:
                    import numpy as np
                    audio, sr, _rms = ret
                    arr = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
                    rms = float(np.sqrt(np.mean(arr ** 2)))
                    if rms < 50:
                        result, colour = f"RMS {rms:.0f} — silent (wrong device?)", "#C0392B"
                    elif rms < 300:
                        result, colour = f"RMS {rms:.0f} — quiet (speak louder)", "#E8771A"
                    else:
                        result, colour = f"RMS {rms:.0f} — OK", "#2EA043"
            except Exception as e:
                result, colour = f"error: {e}", "#C0392B"

            # Update label from worker thread via bridge signal
            self._bridge.event_log_entry.emit(f"[MicTest] {result}")
            # Qt label must be updated from main thread — use a QTimer single-shot
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: (
                self._lbl_mic_rms.setText(result),
                self._lbl_mic_rms.setStyleSheet(f"color: {colour};"),
            ))

        threading.Thread(target=_run, daemon=True).start()

    def _save_settings(self) -> None:
        vc = self._config.setdefault("voice", {})
        vc["enabled"]          = self._chk_voice_enabled.isChecked()
        vc["rate"]             = self._slider_rate.value()
        vc["volume"]           = self._slider_volume.value() / 100.0
        vc["tyre_alerts"]      = self._chk_tyre_alerts.isChecked()
        vc["lap_alerts"]       = self._chk_lap_alerts.isChecked()
        vc["position_alerts"]  = self._chk_pos_alerts.isChecked()
        vc["fuel_alerts"]      = self._chk_fuel_alerts.isChecked()
        vc["countdown_alerts"] = self._chk_countdown.isChecked()
        data = self._combo_voice.currentData()
        if isinstance(data, dict):
            engine = str(data.get("engine", "piper")).lower()
            vc["tts_engine"] = engine
            if engine == "piper":
                vc["piper_model"] = data.get("model", "")
            elif data.get("voice_id"):
                vc["voice_id"] = data.get("voice_id", "")
        elif data:  # legacy: bare SAPI voice id
            vc["voice_id"] = data

        fc = self._config.setdefault("fuel", {})
        fc["safety_margin_laps"]  = self._spin_safety.value()
        fc["pit_threshold_liters"] = self._spin_pit_thr.value()

        cc = self._config.setdefault("connection", {})
        cc["host"] = self._edit_host.text()
        cc["port"] = self._spin_port.value()

        qc = self._config.setdefault("query", {})
        qc["speech_backend"] = self._combo_speech_backend.currentData()
        qc["mic_index"]      = self._combo_microphone.currentData()
        qc["record_secs"]    = self._spin_record_secs.value()
        # query_button is written live on detect — no widgets to read here

        if hasattr(self, "_dev_mode_check"):
            self._config["developer_mode"] = self._dev_mode_check.isChecked()

        self._persist_config()
        self._announcer.update_config(vc)
        self._bridge.event_log_entry.emit("Settings saved.")

    def _reset_settings(self) -> None:
        self._chk_voice_enabled.setChecked(True)
        self._slider_rate.setValue(175)
        self._slider_volume.setValue(100)
        self._spin_safety.setValue(1.0)
        self._spin_pit_thr.setValue(0.5)

    def _populate_voices(self) -> None:
        """Fill the Voice picker with natural (Piper) voices first, then the
        system (SAPI5) voices. Each item carries {engine, model|voice_id} so the
        save path knows which engine to select."""
        self._combo_voice.clear()
        vc = self._config.get("voice", {})
        cur_engine = str(vc.get("tts_engine", "piper")).lower()
        cur_model = vc.get("piper_model", "")
        cur_vid = vc.get("voice_id", "")
        sel = -1

        # Natural (Piper) voices found in voice/piper_models/.
        try:
            from voice.piper_tts import list_local_voices
            for v in list_local_voices():
                self._combo_voice.addItem(
                    f"\U0001F3A4 {v['label']}  (Natural)",
                    {"engine": "piper", "model": v["name"]})
                if cur_engine == "piper" and sel < 0 and (
                        not cur_model or v["name"] == cur_model):
                    sel = self._combo_voice.count() - 1
        except Exception:
            pass

        # System (SAPI5) voices.
        try:
            for vid, vname in (self._announcer.list_voices() or []):
                self._combo_voice.addItem(
                    f"{vname}  (System)", {"engine": "sapi5", "voice_id": vid})
                if cur_engine != "piper" and vid == cur_vid:
                    sel = self._combo_voice.count() - 1
        except Exception:
            pass

        if self._combo_voice.count() == 0:
            self._combo_voice.addItem("Default", {"engine": "sapi5", "voice_id": ""})
        self._combo_voice.setCurrentIndex(sel if sel >= 0 else 0)

    _PIPER_CATALOG = [
        ("Alan — British male (medium)", "en_GB-alan-medium"),
        ("Northern English male (medium)", "en_GB-northern_english_male-medium"),
        ("Ryan — US male (high quality)", "en_US-ryan-high"),
        ("Lessac — US neutral (medium)", "en_US-lessac-medium"),
        ("Cori — British female (high)", "en_GB-cori-high"),
        ("Alba — Scottish female (medium)", "en_GB-alba-medium"),
        ("Jenny — British female (medium)", "en_GB-jenny_dioco-medium"),
    ]

    def _on_download_piper_voice(self) -> None:
        """Download an additional Piper voice from the official catalog into
        voice/piper_models/ (background thread), then refresh the picker."""
        from PyQt6.QtWidgets import QInputDialog
        labels = [c[0] for c in self._PIPER_CATALOG]
        choice, ok = QInputDialog.getItem(
            self, "Download voice",
            "Choose a natural voice to download (~30–110 MB, one-time; runs "
            "offline after):", labels, 0, False)
        if not ok or not choice:
            return
        name = dict(self._PIPER_CATALOG).get(choice, "")
        if not name:
            return
        self._btn_download_voice.setEnabled(False)
        self._btn_download_voice.setText("Downloading…")
        self._bridge.event_log_entry.emit(f"[Voice] downloading {name} …")

        def _run() -> None:
            err = ""
            try:
                from pathlib import Path
                from piper.download_voices import download_voice
                d = Path("voice/piper_models")
                d.mkdir(parents=True, exist_ok=True)
                download_voice(name, d)
            except Exception as e:
                err = str(e)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._on_voice_download_done(name, err))

        import threading as _th
        _th.Thread(target=_run, daemon=True, name="PiperDownload").start()

    def _on_voice_download_done(self, name: str, err: str) -> None:
        self._btn_download_voice.setEnabled(True)
        self._btn_download_voice.setText("Download voice…")
        if err:
            self._bridge.event_log_entry.emit(f"[Voice] download failed: {err}")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Download failed",
                                f"Could not download {name}:\n{err}")
            return
        self._bridge.event_log_entry.emit(f"[Voice] {name} installed.")
        self._populate_voices()
        for i in range(self._combo_voice.count()):
            d = self._combo_voice.itemData(i)
            if isinstance(d, dict) and d.get("model") == name:
                self._combo_voice.setCurrentIndex(i)
                break
