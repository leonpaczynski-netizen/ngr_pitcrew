"""PracticeOutcome — telemetry↔feedback reconciliation + adaptive next action (F3.4).

After a run, the driver sees: the experiment verdict (improved / worse / unchanged /
inconclusive — worse is prominent), telemetry findings, their own feedback, where the
two agree and where they contradict, confidence, and what changed vs the previous run.
The primary action ADAPTS to the verdict (Keep change / Revert / Refine / Gather more /
Build next / Prepare qualifying). Pure presentation over a VM the caller maps from the
canonical reconciliation (setup_diagnosis + outcome verification); it judges nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading
from ui.components.status import StatusPill, ConfidenceMeter
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton


@dataclass(frozen=True)
class PracticeOutcomeVM:
    verdict: str = ""                    # improved|worse|unchanged|inconclusive
    verdict_summary: str = ""
    telemetry_findings: Tuple[str, ...] = field(default_factory=tuple)
    feedback_summary: str = ""
    agreements: Tuple[str, ...] = field(default_factory=tuple)
    contradictions: Tuple[str, ...] = field(default_factory=tuple)
    changed_vs_previous: Tuple[str, ...] = field(default_factory=tuple)
    confidence: str = "unknown"
    primary_action_label: str = ""
    primary_action_key: str = ""         # keep|revert|refine|gather|build_next|to_qualifying
    secondary_action_label: str = ""
    secondary_action_key: str = ""

    @property
    def has_outcome(self) -> bool:
        return bool(self.verdict)


class PracticeOutcome(QWidget):
    action_requested = pyqtSignal(str)   # primary or secondary action key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrPracticeOutcome")
        self._vm = PracticeOutcomeVM()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_t.SPACE_MD)

        head = QHBoxLayout()
        head.addWidget(SectionHeading("RUN OUTCOME", level=2))
        head.addSpacing(_t.SPACE_MD)
        self._verdict = StatusPill("", tone="neutral")
        head.addWidget(self._verdict)
        head.addStretch(1)
        self._confidence = ConfidenceMeter("unknown")
        head.addWidget(self._confidence)
        lay.addLayout(head)

        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_H3}pt;")
        lay.addWidget(self._summary)

        self._telemetry = _section_label()
        lay.addWidget(self._telemetry)
        self._feedback = _section_label()
        lay.addWidget(self._feedback)
        self._agreements = _section_label(_t.SUCCESS)
        lay.addWidget(self._agreements)
        self._contradictions = _section_label(_t.WARN)
        lay.addWidget(self._contradictions)
        self._changed = _section_label()
        lay.addWidget(self._changed)

        act = QHBoxLayout()
        self._primary = PrimaryActionButton()
        self._primary.clicked.connect(lambda: self.action_requested.emit(self._vm.primary_action_key))
        self._secondary = SecondaryActionButton()
        self._secondary.clicked.connect(lambda: self.action_requested.emit(self._vm.secondary_action_key))
        act.addWidget(self._primary)
        act.addWidget(self._secondary)
        act.addStretch(1)
        lay.addLayout(act)

        self._empty = QLabel("No run outcome yet — submit your feedback after a run.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        lay.addWidget(self._empty)
        lay.addStretch(1)

        self.set_outcome(PracticeOutcomeVM())

    def set_outcome(self, vm: PracticeOutcomeVM) -> None:
        if not isinstance(vm, PracticeOutcomeVM):
            vm = PracticeOutcomeVM()
        self._vm = vm

        if vm.verdict:
            desc = _t.outcome_tone(vm.verdict)
            self._verdict.set_status(desc["label"], tone=desc["tone"], glyph=desc.get("glyph", ""))
            self._verdict.setVisible(True)
        else:
            self._verdict.setVisible(False)
        self._confidence.set_level(vm.confidence)

        self._summary.setText(vm.verdict_summary)
        self._summary.setVisible(bool(vm.verdict_summary))

        _set_list(self._telemetry, "Telemetry findings", vm.telemetry_findings)
        _set_text(self._feedback, "Driver feedback", vm.feedback_summary)
        _set_list(self._agreements, "Agrees with telemetry", vm.agreements)
        _set_list(self._contradictions, "Contradictions", vm.contradictions)
        _set_list(self._changed, "Changed vs previous run", vm.changed_vs_previous)

        self._primary.set_action(vm.primary_action_label, enabled=bool(vm.primary_action_label))
        self._secondary.set_action(vm.secondary_action_label, enabled=bool(vm.secondary_action_label))

        self._confidence.setVisible(vm.has_outcome)
        self._empty.setVisible(not vm.has_outcome)


def _section_label(colour: str = "") -> QLabel:
    lbl = QLabel("")
    lbl.setWordWrap(True)
    c = colour or _t.TEXT_DIM
    lbl.setStyleSheet(f"color: {c}; font-size: {_t.FS_CAPTION}pt;")
    lbl.setVisible(False)
    return lbl


def _set_list(label: QLabel, caption: str, items) -> None:
    items = tuple(items or ())
    if items:
        label.setText(f"{caption}:  " + "  ·  ".join(str(i) for i in items))
        label.setVisible(True)
    else:
        label.setVisible(False)


def _set_text(label: QLabel, caption: str, text: str) -> None:
    if text:
        label.setText(f"{caption}:  {text}")
        label.setVisible(True)
    else:
        label.setVisible(False)
