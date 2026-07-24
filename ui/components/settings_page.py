"""SettingsPage — native settings in the new shell (F9 finish).

Covers the settings a driver actually touches — connection, voice alerts, and shift
beep — reading/writing the shared config dict so the new shell no longer bounces to
the classic Settings tab for everyday configuration. Save emits ``save_requested``
(the bridge persists via config_paths + applies to the live services). The deeper
classic-only tools (Track Modelling, Event Planner, full Setup Builder editing)
remain one click away via ``open_classic_requested``.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, QCheckBox, QLabel,
)

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading, Card
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton


class SettingsPage(QWidget):
    save_requested = pyqtSignal()
    open_classic_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrSettingsPage")
        # Brighten the auto-generated form-row labels (inline-styled labels keep theirs).
        self.setStyleSheet(f"#ngrSettingsPage QLabel {{ color: {_t.TEXT}; font-size: {_t.FS_BODY}pt; }}")
        self._config: dict = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        lay.setSpacing(_t.SPACE_MD)
        lay.addWidget(SectionHeading("SETTINGS", level=1))

        # Connection
        conn = Card()
        conn.add(_cap("Connection"))
        cf = QFormLayout()
        self._host = QLineEdit()
        self._port = QSpinBox(); self._port.setRange(1024, 65535)
        cf.addRow("Host", self._host)
        cf.addRow("Port", self._port)
        conn.body.addLayout(cf)
        lay.addWidget(conn)

        # Voice alerts
        voice = Card()
        voice.add(_cap("Voice alerts"))
        vf = QFormLayout()
        self._voice_enabled = QCheckBox()
        self._voice_rate = QSpinBox(); self._voice_rate.setRange(100, 250)
        self._voice_volume = QSpinBox(); self._voice_volume.setRange(0, 100)
        self._tyre_alerts = QCheckBox()
        self._lap_alerts = QCheckBox()
        self._fuel_alerts = QCheckBox()
        vf.addRow("Enabled", self._voice_enabled)
        vf.addRow("Speech rate (wpm)", self._voice_rate)
        vf.addRow("Volume (%)", self._voice_volume)
        vf.addRow("Tyre alerts", self._tyre_alerts)
        vf.addRow("Lap alerts", self._lap_alerts)
        vf.addRow("Fuel / pit alerts", self._fuel_alerts)
        voice.body.addLayout(vf)
        lay.addWidget(voice)

        # Shift beep. The RPM now lives WITH each setup in the Garage (a race tune may
        # short-shift where qualifying runs to the indicator), so here we own only the
        # global on/off and show the current per-discipline points read-only.
        beep = Card()
        beep.add(_cap("Shift beep"))
        bf = QFormLayout()
        self._beep_enabled = QCheckBox()
        self._qual_rpm = QSpinBox(); self._qual_rpm.setRange(0, 20000)
        self._race_rpm = QSpinBox(); self._race_rpm.setRange(0, 20000)
        self._qual_rpm.setSpecialValueText("Not set")
        self._race_rpm.setSpecialValueText("Not set")
        for s in (self._qual_rpm, self._race_rpm):
            s.setReadOnly(True)
            s.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            s.setFocusPolicy(_focus_none())
        bf.addRow("Enabled", self._beep_enabled)
        bf.addRow("Qualifying RPM", self._qual_rpm)
        bf.addRow("Race RPM", self._race_rpm)
        beep.body.addLayout(bf)
        beep.add(_hint("Set the RPM per setup in the Garage — it travels with the "
                       "setup and the beep uses whichever matches your session."))
        lay.addWidget(beep)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {_t.SUCCESS}; font-size: {_t.FS_CAPTION}pt;")
        lay.addWidget(self._status)

        from PyQt6.QtWidgets import QHBoxLayout
        act = QHBoxLayout()
        self._save = PrimaryActionButton("Save settings")
        self._save.clicked.connect(self._on_save)
        self._classic = SecondaryActionButton("Advanced classic tools")
        self._classic.clicked.connect(lambda: self.open_classic_requested.emit())
        act.addWidget(self._save)
        act.addWidget(self._classic)
        act.addStretch(1)
        lay.addLayout(act)
        lay.addStretch(1)

    # ---- populate / collect ----------------------------------------------
    def set_config(self, config: Optional[dict]) -> None:
        self._config = config if isinstance(config, dict) else {}
        c = self._config
        conn = c.get("connection", {}) if isinstance(c.get("connection"), dict) else {}
        self._host.setText(str(conn.get("host", "127.0.0.1")))
        self._port.setValue(int(conn.get("port", 33741) or 33741))
        vc = c.get("voice", {}) if isinstance(c.get("voice"), dict) else {}
        self._voice_enabled.setChecked(bool(vc.get("enabled", True)))
        self._voice_rate.setValue(int(vc.get("rate", 175) or 175))
        self._voice_volume.setValue(int(float(vc.get("volume", 1.0) or 1.0) * 100))
        self._tyre_alerts.setChecked(bool(vc.get("tyre_alerts", True)))
        self._lap_alerts.setChecked(bool(vc.get("lap_alerts", True)))
        self._fuel_alerts.setChecked(bool(vc.get("fuel_alerts", True)))
        sb = c.get("shift_beep", {}) if isinstance(c.get("shift_beep"), dict) else {}
        self._beep_enabled.setChecked(bool(sb.get("enabled", True)))
        self._qual_rpm.setValue(int(sb.get("qual_rpm", 0) or 0))
        self._race_rpm.setValue(int(sb.get("race_rpm", 0) or 0))
        self._status.setText("")

    def apply_to_config(self) -> dict:
        """Write the edited values back into the shared config dict; returns it."""
        c = self._config
        c.setdefault("connection", {})
        c["connection"]["host"] = self._host.text().strip() or "127.0.0.1"
        c["connection"]["port"] = int(self._port.value())
        c.setdefault("voice", {})
        c["voice"]["enabled"] = bool(self._voice_enabled.isChecked())
        c["voice"]["rate"] = int(self._voice_rate.value())
        c["voice"]["volume"] = float(self._voice_volume.value()) / 100.0
        c["voice"]["tyre_alerts"] = bool(self._tyre_alerts.isChecked())
        c["voice"]["lap_alerts"] = bool(self._lap_alerts.isChecked())
        c["voice"]["fuel_alerts"] = bool(self._fuel_alerts.isChecked())
        c.setdefault("shift_beep", {})
        c["shift_beep"]["enabled"] = bool(self._beep_enabled.isChecked())
        # The RPM values are owned by the Garage sheets; Settings shows them read-only
        # and must not write them back (which would clobber a sheet-set value with a
        # stale display copy). Only the on/off is written here.
        return c

    def _on_save(self) -> None:
        self.apply_to_config()
        self.save_requested.emit()

    def show_saved(self, ok: bool = True) -> None:
        self._status.setText("Settings saved." if ok else "Could not save settings.")
        self._status.setStyleSheet(
            f"color: {_t.SUCCESS if ok else _t.DANGER}; font-size: {_t.FS_CAPTION}pt;")


def _cap(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_t.NGR_GREEN}; font-weight: 700; font-size: {_t.FS_CAPTION}pt;")
    return lbl


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
    return lbl


def _focus_none():
    from PyQt6.QtCore import Qt
    return Qt.FocusPolicy.NoFocus
