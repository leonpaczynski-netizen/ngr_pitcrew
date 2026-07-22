"""Status widgets: StatusPill and ConfidenceMeter (F0.5).

Both convey meaning by colour + text (+ glyph) together, never colour alone — the
accessible name/tooltip always carries the full label so a screen reader and a
colour-blind user get the same information.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout, QProgressBar

from ui import ngr_theme as _t


# Map a semantic tone key to its vivid base colour (for bars, dots, edges).
TONE_BASE_COLOR: dict[str, str] = {
    "success": _t.SUCCESS,
    "info": _t.INFO,
    "warn": _t.WARN,
    "danger": _t.DANGER,
    "neutral": _t.NEUTRAL,
    "advisory": _t.ADVISORY_EDGE,
}


class StatusPill(QLabel):
    """A small rounded status pill in a semantic tone.

    ``set_status(text, tone, glyph)`` restyles it. The full text is set as the
    tooltip/accessible name so meaning never depends on colour alone.
    """

    def __init__(self, text: str = "", tone: str = "neutral", glyph: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("ngrStatusPill")
        self._tone = "neutral"
        self.set_status(text, tone, glyph)

    def set_status(self, text: str, tone: str = "neutral", glyph: str = "") -> None:
        self._tone = tone if tone in _t.STATUS_TONES else "neutral"
        text = text or ""
        display = f"{glyph} {text}".strip() if glyph else text
        self.setText(display)
        self.setStyleSheet(_t.badge_qss(self._tone))
        self.setToolTip(text)
        self.setAccessibleName(text)

    @property
    def tone(self) -> str:
        return self._tone


class ConfidenceMeter(QWidget):
    """A compact confidence indicator: a filled bar + explicit label.

    Fed a confidence key ('high'|'medium'|'low'|'unknown'); resolves via
    ``ngr_theme.confidence_level`` so colour, label and 0..1 fill stay in one
    place. Never raises on an unknown key (falls back to 'unknown').
    """

    def __init__(self, level: str = "unknown", parent=None):
        super().__init__(parent)
        self.setObjectName("ngrConfidenceMeter")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_t.SPACE_SM)

        self._bar = QProgressBar(self)
        self._bar.setObjectName("ngrConfidenceBar")
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setMaximumWidth(72)

        self._label = QLabel(self)
        self._label.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")

        lay.addWidget(self._bar)
        lay.addWidget(self._label)
        lay.addStretch(1)

        self._level = "unknown"
        self.set_level(level)

    def set_level(self, level: str) -> None:
        desc = _t.confidence_level(level)
        self._level = (level or "unknown").lower()
        fill = int(round(float(desc.get("fill", 0.0)) * 100))
        self._bar.setValue(fill)
        base = TONE_BASE_COLOR.get(desc.get("tone", "neutral"), _t.NEUTRAL)
        # Unknown/zero-evidence renders as a hatched-empty neutral track.
        self._bar.setStyleSheet(
            f"QProgressBar#ngrConfidenceBar {{ background: {_t.CARBON_HI}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: 3px; }}"
            f"QProgressBar#ngrConfidenceBar::chunk {{ background: {base}; "
            f"border-radius: 3px; }}"
        )
        self._label.setText(f"Confidence: {desc.get('label', 'No evidence')}")
        self.setToolTip(f"Confidence: {desc.get('label', 'No evidence')}")
        self.setAccessibleName(self._label.text())

    def value(self) -> int:
        """Current bar fill 0..100 (for tests)."""
        return self._bar.value()

    @property
    def level(self) -> str:
        return self._level
