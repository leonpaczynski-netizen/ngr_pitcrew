"""QualifyingReadiness — the qualifying readiness checklist (F4).

A checklist where every item shows status by colour + icon + text (never colour
alone): qualifying setup selected, Soft tyres confirmed, fuel target, gearbox
objective, track limits, out-lap / tyre-prep / push-lap / traffic plans, risk
corners, driver confidence, remaining blockers. The engineer explains what changed
from practice, why it gives one-lap pace, what to protect, and the compromised-lap
fallback. Primary action Begin Qualifying is enabled only when nothing blocks it.
Pure presentation over a VM the caller maps from setup_strategy_readiness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QGridLayout

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading, Card
from ui.components.buttons import PrimaryActionButton


# status -> (tone, glyph)
_STATUS = {
    "ok":      ("success", "✓"),
    "blocked": ("danger", "✕"),
    "warn":    ("warn", "!"),
    "na":      ("neutral", "–"),
}


@dataclass(frozen=True)
class ReadinessItem:
    label: str
    status: str = "na"     # ok|blocked|warn|na
    note: str = ""


@dataclass(frozen=True)
class QualifyingReadinessVM:
    items: Tuple[ReadinessItem, ...] = field(default_factory=tuple)
    explanation: str = ""              # engineer: what changed / why one-lap pace / protect / fallback
    blockers: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        return bool(self.items) and not self.blockers and not any(
            i.status == "blocked" for i in self.items)


class QualifyingReadiness(QWidget):
    begin_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrQualiReadiness")
        self._vm = QualifyingReadinessVM()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        lay.setSpacing(_t.SPACE_MD)

        top = QHBoxLayout()
        top.addWidget(SectionHeading("QUALIFYING", level=1))
        top.addSpacing(_t.SPACE_MD)
        sub = QLabel("Am I ready?")
        sub.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        top.addWidget(sub)
        top.addStretch(1)
        lay.addLayout(top)

        # Checklist grid (status glyph | label | note)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(_t.SPACE_MD)
        self._grid.setVerticalSpacing(_t.SPACE_XS)
        self._grid.setColumnStretch(2, 1)
        lay.addLayout(self._grid)

        # Engineer explanation
        self._explain_card = Card()
        self._explain_title = QLabel("Engineer")
        self._explain_title.setStyleSheet(
            f"color: {_t.NGR_GREEN}; font-weight: 700; font-size: {_t.FS_CAPTION}pt;")
        self._explain = QLabel("")
        self._explain.setWordWrap(True)
        self._explain.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_BODY}pt;")
        self._explain_card.add(self._explain_title)
        self._explain_card.add(self._explain)
        lay.addWidget(self._explain_card)

        self._blockers = QLabel("")
        self._blockers.setWordWrap(True)
        self._blockers.setStyleSheet(f"color: {_t.WARN}; font-size: {_t.FS_CAPTION}pt; font-weight: 600;")
        self._blockers.setVisible(False)
        lay.addWidget(self._blockers)

        act = QHBoxLayout()
        self._begin = PrimaryActionButton()
        self._begin.clicked.connect(lambda: self.begin_requested.emit())
        act.addWidget(self._begin)
        act.addStretch(1)
        lay.addLayout(act)
        lay.addStretch(1)

        self.set_readiness(QualifyingReadinessVM())

    def set_readiness(self, vm: QualifyingReadinessVM) -> None:
        if not isinstance(vm, QualifyingReadinessVM):
            vm = QualifyingReadinessVM()
        self._vm = vm

        _clear_grid(self._grid)
        for row, item in enumerate(vm.items):
            tone, glyph = _STATUS.get(item.status, _STATUS["na"])
            from ui.components.status import TONE_BASE_COLOR
            g = QLabel(glyph)
            g.setStyleSheet(
                f"color: {TONE_BASE_COLOR.get(tone, _t.NEUTRAL)}; "
                f"font-weight: 700; font-size: {_t.FS_LABEL}pt;")
            g.setFixedWidth(18)
            g.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl = QLabel(item.label)
            lbl.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_BODY}pt;")
            note = QLabel(item.note)
            note.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
            note.setWordWrap(True)
            self._grid.addWidget(g, row, 0)
            self._grid.addWidget(lbl, row, 1)
            self._grid.addWidget(note, row, 2)

        self._explain.setText(vm.explanation)
        self._explain_card.setVisible(bool(vm.explanation))

        if vm.blockers:
            self._blockers.setText("Remaining blockers:  " + "  ·  ".join(vm.blockers))
            self._blockers.setVisible(True)
        else:
            self._blockers.setVisible(False)

        self._begin.set_action("Begin Qualifying", enabled=vm.ready)


def _clear_grid(grid) -> None:
    while grid.count():
        item = grid.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
