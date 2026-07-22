"""DebriefView — the post-session debrief (F7.1).

After every session the driver sees what happened, what was learned, what improved
and what regressed (regressions prominent), which predictions were right or wrong,
new evidence, contradictions, the setup and strategy outcomes, driver/track/corner
findings, and knowledge-maturity changes. Failed experiments stay visible. The
primary action reflects the programme state (Continue development / Prepare
qualifying / Prepare race / Close event / Post-event review). Pure presentation over
a VM the caller maps from binding_debrief_workflow + build_cross_session_memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading
from ui.components.buttons import PrimaryActionButton


@dataclass(frozen=True)
class DebriefVM:
    what_happened: str = ""
    improved: Tuple[str, ...] = field(default_factory=tuple)
    regressed: Tuple[str, ...] = field(default_factory=tuple)
    learned: Tuple[str, ...] = field(default_factory=tuple)
    predictions_correct: Tuple[str, ...] = field(default_factory=tuple)
    predictions_wrong: Tuple[str, ...] = field(default_factory=tuple)
    new_evidence: Tuple[str, ...] = field(default_factory=tuple)
    contradictions: Tuple[str, ...] = field(default_factory=tuple)
    setup_outcome: str = ""
    strategy_outcome: str = ""
    findings: Tuple[str, ...] = field(default_factory=tuple)     # driver/track/corner
    maturity_changes: Tuple[str, ...] = field(default_factory=tuple)
    carry_forward: Tuple[str, ...] = field(default_factory=tuple)
    primary_action_label: str = ""
    primary_action_key: str = ""

    @property
    def has_debrief(self) -> bool:
        return bool(self.what_happened or self.improved or self.regressed or self.learned)


class DebriefView(QWidget):
    action_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrDebrief")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        self._root.setSpacing(_t.SPACE_SM)

        top = QHBoxLayout()
        top.addWidget(SectionHeading("DEBRIEF", level=1))
        top.addSpacing(_t.SPACE_MD)
        sub = QLabel("What did we learn?")
        sub.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        top.addWidget(sub)
        top.addStretch(1)
        self._root.addLayout(top)

        self._happened = QLabel("")
        self._happened.setWordWrap(True)
        self._happened.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_H3}pt;")
        self._root.addWidget(self._happened)

        self._body = QVBoxLayout()
        self._body.setSpacing(_t.SPACE_XS)
        self._root.addLayout(self._body)

        self._empty = QLabel("No debrief yet — complete a session to generate one.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        self._root.addWidget(self._empty)

        act = QHBoxLayout()
        self._primary = PrimaryActionButton()
        self._primary.clicked.connect(lambda: self.action_requested.emit(self._vm.primary_action_key))
        act.addWidget(self._primary)
        act.addStretch(1)
        self._root.addLayout(act)
        self._root.addStretch(1)

        self._vm = DebriefVM()
        self.set_debrief(DebriefVM())

    def set_debrief(self, vm: DebriefVM) -> None:
        if not isinstance(vm, DebriefVM):
            vm = DebriefVM()
        self._vm = vm
        _clear_layout(self._body)

        self._happened.setText(vm.what_happened)
        self._happened.setVisible(bool(vm.what_happened))
        self._empty.setVisible(not vm.has_debrief)

        # Colour-coded sections; regressions & wrong predictions are prominent.
        self._section("Improved", vm.improved, _t.SUCCESS)
        self._section("Regressed", vm.regressed, _t.DANGER)
        self._section("Learned", vm.learned, _t.TEXT)
        self._section("Predictions correct", vm.predictions_correct, _t.SUCCESS)
        self._section("Predictions wrong", vm.predictions_wrong, _t.WARN)
        self._section("New evidence", vm.new_evidence, _t.TEXT_DIM)
        self._section("Contradictions", vm.contradictions, _t.WARN)
        self._line("Setup outcome", vm.setup_outcome)
        self._line("Strategy outcome", vm.strategy_outcome)
        self._section("Findings", vm.findings, _t.TEXT_DIM)
        self._section("Knowledge maturity", vm.maturity_changes, _t.INFO)
        self._section("Carried into next event", vm.carry_forward, _t.NGR_GREEN)

        self._primary.set_action(vm.primary_action_label, enabled=bool(vm.primary_action_label))

    def _section(self, caption: str, items, colour: str) -> None:
        items = tuple(items or ())
        if not items:
            return
        cap = QLabel(caption)
        cap.setStyleSheet(f"color: {colour}; font-weight: 700; font-size: {_t.FS_CAPTION}pt;")
        self._body.addWidget(cap)
        body = QLabel("• " + "\n• ".join(str(i) for i in items))
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_CAPTION}pt;")
        self._body.addWidget(body)

    def _line(self, caption: str, text: str) -> None:
        if not text:
            return
        lbl = QLabel(f"{caption}:  {text}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_CAPTION}pt;")
        self._body.addWidget(lbl)


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
