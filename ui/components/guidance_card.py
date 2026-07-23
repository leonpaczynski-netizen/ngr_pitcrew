"""EngineerGuidanceCard — the primary Pit Crew Engineer guidance surface (F0.5/F1).

Renders an ``EngineerGuidanceVM``: an engineer message, the current objective, an
evidence summary + confidence, any warnings (never hidden), the single dominant
primary action, an optional quiet secondary action, an expandable explanation, and
a read-aloud hook. It computes nothing — it renders the VM the domain produced.

Signals:
  * ``primary_requested(str surface)``  — user pressed the primary CTA
  * ``secondary_requested(str surface)`` — user pressed the secondary action
  * ``read_aloud_requested(str text)``  — user asked the engineer to speak
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel, QHBoxLayout, QVBoxLayout, QToolButton, QWidget, QSizePolicy,
)

from ui import ngr_theme as _t
from ui.components.cards import Card, SectionHeading
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton
from ui.components.status import ConfidenceMeter
from ui.components.guidance_vm import EngineerGuidanceVM


class EngineerGuidanceCard(Card):
    primary_requested = pyqtSignal(str)
    secondary_requested = pyqtSignal(str)
    read_aloud_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrGuidanceCard")
        self._vm = EngineerGuidanceVM.empty()

        # Header: engineer label + read-aloud
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._title = SectionHeading("PIT CREW ENGINEER", level=3)
        self._read_btn = QToolButton()
        self._read_btn.setText("Read aloud")
        self._read_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._read_btn.setStyleSheet(
            f"QToolButton {{ color: {_t.NGR_GREEN}; background: transparent; "
            f"border: none; font-size: {_t.FS_CAPTION}pt; }}"
            f"QToolButton:hover {{ color: {_t.NGR_GREEN_HI}; }}"
            f"QToolButton:focus {{ {_t.focus_ring_qss()} }}"
        )
        self._read_btn.clicked.connect(self._on_read)
        header.addWidget(self._title)
        header.addStretch(1)
        header.addWidget(self._read_btn)
        self.body.addLayout(header)

        # Engineer message (the explanatory line)
        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_H3}pt;")
        self.body.addWidget(self._message)

        # What is actually on the car — so the driver's applied setup is acknowledged
        # rather than the card reading as if nothing had been done.
        self._active_setup = QLabel()
        self._active_setup.setWordWrap(True)
        self._active_setup.setStyleSheet(
            f"color: {_t.SUCCESS}; font-size: {_t.FS_CAPTION}pt; font-weight: 600;")
        self._active_setup.setVisible(False)
        self.body.addWidget(self._active_setup)

        # Objective
        self._objective = QLabel()
        self._objective.setWordWrap(True)
        self._objective.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        self.body.addWidget(self._objective)

        # Evidence + confidence, stacked so neither truncates in the narrow column.
        self._evidence = QLabel()
        self._evidence.setWordWrap(True)
        self._evidence.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self.body.addWidget(self._evidence)
        self._confidence = ConfidenceMeter("unknown")
        self.body.addWidget(self._confidence)

        # Warnings (hidden unless present) — never suppressed when domain has them.
        self._warnings = QLabel()
        self._warnings.setWordWrap(True)
        self._warnings.setStyleSheet(
            f"color: {_t.WARN}; font-size: {_t.FS_CAPTION}pt; font-weight: 600;"
        )
        self._warnings.setVisible(False)
        self.body.addWidget(self._warnings)

        # Actions. Stacked full-width, NOT side by side: the guidance column is a
        # fixed 360px and a real CTA label ("Build setup_base evidence") was being
        # centre-clipped to "ld setup_base evide" when the two shared one row.
        act_col = QVBoxLayout()
        act_col.setContentsMargins(0, _t.SPACE_XS, 0, 0)
        act_col.setSpacing(_t.SPACE_XS)
        self._primary = PrimaryActionButton()
        self._primary.clicked.connect(self._on_primary)
        self._secondary = SecondaryActionButton()
        self._secondary.clicked.connect(self._on_secondary)
        for b in (self._primary, self._secondary):
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            act_col.addWidget(b)
        self.body.addLayout(act_col)

        # Expandable explanation
        self._expander = QToolButton()
        self._expander.setText("▸ Why this")
        self._expander.setCheckable(True)
        self._expander.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expander.setStyleSheet(
            f"QToolButton {{ color: {_t.TEXT_DIM}; background: transparent; "
            f"border: none; font-size: {_t.FS_CAPTION}pt; }}"
            f"QToolButton:hover {{ color: {_t.TEXT_HI}; }}"
            f"QToolButton:focus {{ {_t.focus_ring_qss()} }}"
        )
        self._expander.toggled.connect(self._on_expand)

        # Transient status from the caller (e.g. why Read aloud stayed silent).
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {_t.WARN}; font-size: {_t.FS_CAPTION}pt;")
        self._status.setVisible(False)
        self.body.addWidget(self._status)
        self._explanation = QLabel()
        self._explanation.setWordWrap(True)
        self._explanation.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._explanation.setVisible(False)
        self.body.addWidget(self._expander)
        self.body.addWidget(self._explanation)

        self.set_vm(self._vm)

    # ---- population -------------------------------------------------------
    def set_vm(self, vm: EngineerGuidanceVM) -> None:
        """Render a guidance VM. Defensive against a None/garbage vm."""
        if not isinstance(vm, EngineerGuidanceVM):
            vm = EngineerGuidanceVM.empty()
        self._vm = vm

        self._message.setText(vm.message)
        self._active_setup.setText(f"✓ On the car: {vm.active_setup}" if vm.active_setup else "")
        self._active_setup.setVisible(bool(vm.active_setup))
        self._objective.setText(f"Objective: {vm.objective}" if vm.objective else "")
        self._objective.setVisible(bool(vm.objective))

        self._evidence.setText(f"Evidence: {vm.evidence_summary}" if vm.evidence_summary else "")
        self._evidence.setVisible(bool(vm.evidence_summary))
        self._confidence.set_level(vm.confidence_level)

        if vm.warnings:
            self._warnings.setText("⚠ " + "  ·  ".join(vm.warnings))
            self._warnings.setVisible(True)
        else:
            self._warnings.setText("")
            self._warnings.setVisible(False)

        self._primary.set_action(vm.primary_action_label, enabled=bool(vm.primary_action_label))
        self._secondary.set_action(vm.secondary_action_label, enabled=bool(vm.secondary_action_label))

        has_expl = bool(vm.explanation)
        self._expander.setVisible(has_expl)
        if not has_expl:
            self._expander.setChecked(False)
            self._explanation.setVisible(False)
        self._explanation.setText(vm.explanation)

    def set_status(self, text: str) -> None:
        """Show (or clear, with "") a caller-supplied status line under the card."""
        text = str(text or "")
        self._status.setText(text)
        self._status.setVisible(bool(text))

    # ---- signal plumbing --------------------------------------------------
    def _on_primary(self):
        self.primary_requested.emit(self._vm.primary_action_surface)

    def _on_secondary(self):
        self.secondary_requested.emit(self._vm.secondary_action_surface)

    def _on_read(self):
        self.read_aloud_requested.emit(self._vm.read_aloud_text or self._vm.message)

    def _on_expand(self, checked: bool):
        self._explanation.setVisible(bool(checked))
        self._expander.setText("▾ Why this" if checked else "▸ Why this")
