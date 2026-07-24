"""StructuredFeedbackForm — Practice Review driver feedback (F3.2).

Feedback is captured through segmented controls / dropdowns / scales and a corner
selector — NOT free text first (free text only supplements). The most important
signal, "better or worse than the previous setup", is prominent. Submitting emits a
structured ``{field: value}`` dict the caller reconciles against telemetry via the
canonical setup-diagnosis feedback pipeline; this widget captures, it does not judge.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QToolButton, QButtonGroup, QLineEdit,
)

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading
from ui.components.buttons import PrimaryActionButton


# Overall verdict — the prominent segmented control.
OVERALL_OPTIONS: Tuple[Tuple[str, str], ...] = (
    ("better", "Better than previous"),
    ("unchanged", "Unchanged"),
    ("worse", "Worse than previous"),
)

_BALANCE = ["", "Strong understeer", "Understeer", "Neutral", "Oversteer", "Strong oversteer"]
_SCALE = ["", "Poor", "Below par", "OK", "Good", "Excellent"]
_SEVERITY = ["", "None", "Minor", "Noticeable", "Severe"]
_GEAR = ["", "Too short", "About right", "Too long"]
_VS_EXPECT = ["", "Better than expected", "As expected", "Worse than expected"]

# (field_key, label, options) — grouped for a two-column grid.
FEEDBACK_FIELDS: Tuple[Tuple[str, str, List[str]], ...] = (
    ("corner_entry", "Entry balance", _BALANCE),
    ("mid_corner", "Mid-corner balance", _BALANCE),
    ("exit_stability", "Exit balance", _BALANCE),
    ("braking_confidence", "Braking confidence", _SCALE),
    ("traction", "Traction", _SCALE),
    ("rotation", "Rotation", _SCALE),
    ("drive_out", "Drive-out", _SCALE),
    ("straight_line", "Straight-line", _SCALE),
    ("kerb_behaviour", "Kerb behaviour", _SEVERITY),
    ("bottoming", "Bottoming", _SEVERITY),
    ("gear_choice", "Gear choice", _GEAR),
    ("fuel_behaviour", "Fuel", _VS_EXPECT),
    ("tyre_condition", "Tyre behaviour", _VS_EXPECT),
    ("confidence", "Overall confidence", _SCALE),
)


class StructuredFeedbackForm(QWidget):
    submitted = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrFeedbackForm")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_t.SPACE_MD)

        lay.addWidget(SectionHeading("PRACTICE REVIEW", level=2))

        # Prominent overall verdict (segmented)
        prompt = QLabel("Versus the previous setup:")
        prompt.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_H3}pt; font-weight: 600;")
        lay.addWidget(prompt)
        overall_row = QHBoxLayout()
        overall_row.setSpacing(2)
        self._overall_group = QButtonGroup(self)
        self._overall_group.setExclusive(True)
        self._overall_buttons: Dict[str, QToolButton] = {}
        self._overall_value = ""
        for key, label in OVERALL_OPTIONS:
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(_t.TOUCH_MIN_H)
            b.setStyleSheet(self._overall_qss(key))
            b.clicked.connect(lambda _=False, k=key: self._set_overall(k))
            self._overall_group.addButton(b)
            self._overall_buttons[key] = b
            overall_row.addWidget(b)
        overall_row.addStretch(1)
        lay.addLayout(overall_row)

        # Structured detail grid (two columns of label + combo)
        grid = QGridLayout()
        grid.setHorizontalSpacing(_t.SPACE_LG)
        grid.setVerticalSpacing(_t.SPACE_XS)
        self._combos: Dict[str, QComboBox] = {}
        half = (len(FEEDBACK_FIELDS) + 1) // 2
        for i, (key, label, options) in enumerate(FEEDBACK_FIELDS):
            col = 0 if i < half else 2
            row = i if i < half else i - half
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_BODY}pt;")
            combo = QComboBox()
            combo.addItems(options)
            combo.setMinimumWidth(150)
            grid.addWidget(lbl, row, col)
            grid.addWidget(combo, row, col + 1)
            self._combos[key] = combo
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        lay.addLayout(grid)

        # Corner selector + free-text supplement
        corner_row = QHBoxLayout()
        corner_lbl = QLabel("Corners / segments")
        corner_lbl.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_BODY}pt;")
        self._corners = QComboBox()
        self._corners.setEditable(True)
        self._corners.setMinimumWidth(220)
        self._corners.lineEdit().setPlaceholderText("e.g. Turn 6 (Esses), Turn 10")
        corner_row.addWidget(corner_lbl)
        corner_row.addWidget(self._corners)
        corner_row.addStretch(1)
        lay.addLayout(corner_row)

        self._notes = QLineEdit()
        self._notes.setPlaceholderText("Optional notes (supplements the structured feedback above)…")
        lay.addWidget(self._notes)

        act = QHBoxLayout()
        self._submit = PrimaryActionButton("Submit feedback")
        self._submit.clicked.connect(self._on_submit)
        act.addWidget(self._submit)
        act.addStretch(1)
        lay.addLayout(act)

    # ---- corner options ---------------------------------------------------
    def set_corner_options(self, corners) -> None:
        cur = self._corners.currentText()
        self._corners.clear()
        for c in (corners or ()):
            self._corners.addItem(str(c))
        self._corners.setCurrentText(cur)

    # ---- overall ----------------------------------------------------------
    def _set_overall(self, key: str) -> None:
        self._overall_value = key
        b = self._overall_buttons.get(key)
        if b is not None:
            b.setChecked(True)

    def _overall_qss(self, key: str) -> str:
        # 'worse' checks danger-red (negative feedback is authoritative), 'better' green.
        checked_bg = {"better": _t.SUCCESS, "worse": _t.DANGER}.get(key, _t.NEUTRAL)
        checked_fg = _t.INK_BLACK
        return (
            f"QToolButton {{ color: {_t.TEXT_DIM}; background: {_t.CARBON}; "
            f"border: 1px solid {_t.HAIRLINE}; padding: 6px 16px; font-size: {_t.FS_LABEL}pt; }}"
            f"QToolButton:hover {{ color: {_t.TEXT_HI}; }}"
            f"QToolButton:checked {{ color: {checked_fg}; background: {checked_bg}; "
            f"border-color: {checked_bg}; font-weight: 700; }}"
            f"QToolButton:focus {{ {_t.focus_ring_qss()} }}"
        )

    # ---- submit -----------------------------------------------------------
    def current_feedback(self) -> dict:
        fb: dict = {}
        if self._overall_value:
            fb["overall"] = self._overall_value
        for key, combo in self._combos.items():
            v = combo.currentText().strip()
            if v:
                fb[key] = v
        corners = self._corners.currentText().strip()
        if corners:
            fb["corners"] = corners
        notes = self._notes.text().strip()
        if notes:
            fb["notes"] = notes
        return fb

    def _on_submit(self) -> None:
        self.submitted.emit(self.current_feedback())
