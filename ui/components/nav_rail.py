"""NavRail — the persistent left navigation (F1).

Ten top-level destinations, each with a text label (never icon-only), the active
one highlighted with an NGR-green marker. Keyboard-navigable with a visible focus
ring. Emits ``navigate(destination_key)``.

Navigation gating for programme stages lives on the ProgressRail + guidance; the
standing nav destinations here are always reachable so the user can move around
freely (Home, Engineering Library, Settings are never blocked).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QButtonGroup

from ui import ngr_theme as _t
from ui.app_state import NAV_DESTINATIONS


NAV_LABELS: dict[str, str] = {
    "home": "Home",
    "active_event": "Active Event",
    "garage": "Garage",
    "practice": "Practice",
    "qualifying": "Qualifying",
    "race_strategy": "Race Strategy",
    "live_pit_wall": "Live Pit Wall",
    "debrief": "Debrief",
    "track_model": "Track Model",
    "engineering_library": "Engineering Library",
    "settings": "Settings",
}


class NavRail(QWidget):
    navigate = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrNavRail")
        self.setStyleSheet(f"#ngrNavRail {{ background: {_t.INK_BLACK}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(_t.SPACE_XS, _t.SPACE_MD, _t.SPACE_XS, _t.SPACE_MD)
        lay.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        for dest in NAV_DESTINATIONS:
            btn = QToolButton(self)
            btn.setObjectName(f"ngrNav_{dest}")
            btn.setText(NAV_LABELS.get(dest, dest.replace("_", " ").title()))
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setMinimumHeight(_t.TOUCH_MIN_H)
            btn.setStyleSheet(self._btn_qss())
            btn.clicked.connect(lambda _=False, d=dest: self.navigate.emit(d))
            self._group.addButton(btn)
            self._buttons[dest] = btn
            lay.addWidget(btn)
        lay.addStretch(1)

        self.set_active("home")

    def set_active(self, destination: str) -> None:
        """Highlight the current destination without emitting navigate()."""
        btn = self._buttons.get(destination)
        if btn is not None:
            btn.setChecked(True)

    @staticmethod
    def _btn_qss() -> str:
        return (
            f"QToolButton {{ color: {_t.TEXT_DIM}; background: transparent; "
            f"border: none; border-left: 3px solid transparent; "
            f"padding: 6px 12px; text-align: left; font-size: {_t.FS_LABEL}pt; }}"
            f"QToolButton:hover {{ color: {_t.TEXT_HI}; background: {_t.CARBON}; }}"
            f"QToolButton:checked {{ color: {_t.TEXT_HI}; background: {_t.CARBON}; "
            f"border-left: 3px solid {_t.NGR_GREEN}; font-weight: 700; }}"
            f"QToolButton:focus {{ {_t.focus_ring_qss()} }}"
        )
