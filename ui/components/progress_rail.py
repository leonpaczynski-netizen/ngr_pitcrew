"""ProgressRail — the persistent programme journey rail (F1).

Renders the 8 canonical programme stages with their state (complete / current /
available / blocked / not-required) from an AppState. A user can read their event
status in seconds. Navigable stages emit ``stage_selected(stage_key)``; blocked and
not-required stages are visibly distinct and non-navigable (the guidance card
explains *why* — the rail never silently hides a stage).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QToolButton

from ui import ngr_theme as _t
from ui.app_state import AppState, PROGRAMME_STAGES
from ui.components.status import TONE_BASE_COLOR


STAGE_LABELS: dict[str, str] = {
    "briefing": "Briefing",
    "garage": "Garage",
    "practice": "Practice",
    "review": "Review",
    "qualifying": "Qualifying",
    "strategy": "Strategy",
    "race": "Race",
    "debrief": "Debrief",
}


class ProgressRail(QWidget):
    stage_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrProgressRail")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(_t.SPACE_SM, _t.SPACE_XS, _t.SPACE_SM, _t.SPACE_XS)
        lay.setSpacing(_t.SPACE_XS)

        self._nodes: dict[str, QToolButton] = {}
        for key in PROGRAMME_STAGES:
            btn = QToolButton(self)
            btn.setObjectName(f"ngrStage_{key}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.clicked.connect(lambda _=False, k=key: self._on_click(k))
            self._nodes[key] = btn
            lay.addWidget(btn)
        lay.addStretch(1)

        self.set_state(AppState.empty())

    def _on_click(self, key: str) -> None:
        # Only navigable stages emit; blocked/not-required are inert.
        if self._nodes[key].isEnabled():
            self.stage_selected.emit(key)

    def set_state(self, app_state: AppState) -> None:
        if not isinstance(app_state, AppState):
            app_state = AppState.empty()
        for key, btn in self._nodes.items():
            state = app_state.stage_state(key)
            desc = _t.stage_state(state)
            label = STAGE_LABELS.get(key, key.title())
            btn.setText(f"{desc['glyph']}  {label}")
            is_current = app_state.is_current_stage(key)
            navigable = app_state.can_navigate(key)
            btn.setEnabled(navigable)
            # Accessible/tooltip carries the state word — never colour-only.
            btn.setToolTip(f"{label}: {desc['label']}")
            btn.setAccessibleName(f"{label} — {desc['label']}")
            btn.setStyleSheet(self._node_qss(desc, is_current, navigable))

    @staticmethod
    def _node_qss(desc: dict, is_current: bool, navigable: bool) -> str:
        base = TONE_BASE_COLOR.get(desc.get("tone", "neutral"), _t.NEUTRAL)
        if is_current:
            fg = _t.NGR_GREEN
            weight = 700
            border = f"border-bottom: 2px solid {_t.NGR_GREEN};"
        elif navigable:
            fg = base
            weight = 600
            border = "border: none;"
        else:
            fg = _t.TEXT_MUTE
            weight = 500
            border = "border: none;"
        return (
            f"QToolButton {{ color: {fg}; background: transparent; {border} "
            f"padding: 4px 8px; font-size: {_t.FS_CAPTION}pt; font-weight: {weight}; }}"
            f"QToolButton:hover {{ color: {_t.TEXT_HI}; }}"
            f"QToolButton:focus {{ {_t.focus_ring_qss()} }}"
            f"QToolButton:disabled {{ color: {_t.TEXT_MUTE}; }}"
        )
