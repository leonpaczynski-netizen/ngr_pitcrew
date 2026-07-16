"""Qt widget that renders the guided WorkflowState as a stepper (Sprint 10 UI).

Thin presentation over the pure ``ui.workflow_stepper`` state: a horizontal row
of numbered stage chips coloured by status (done / current / blocked / pending),
with the current stage's blocker + the single next action shown prominently
below. No product logic lives here — it only renders a ``WorkflowState``.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QPushButton, QSizePolicy,
)

from ui import ngr_theme as T
from ui.workflow_stepper import WorkflowState, StageStatus

_STATUS_COLOR = {
    StageStatus.DONE: T.SUCCESS,
    StageStatus.CURRENT: T.NGR_GREEN,
    StageStatus.BLOCKED: T.DANGER,
    StageStatus.PENDING: T.NEUTRAL,
}
_STATUS_INK = {
    StageStatus.DONE: T.NGR_GREEN_INK,
    StageStatus.CURRENT: T.NGR_GREEN_INK,
    StageStatus.BLOCKED: "#FFFFFF",
    StageStatus.PENDING: T.CARBON,
}


class _StageChip(QFrame):
    def __init__(self, index: int, title: str, status: StageStatus, parent=None):
        super().__init__(parent)
        self.setObjectName("wf_stage_chip")
        color = _STATUS_COLOR.get(status, T.NEUTRAL)
        ink = _STATUS_INK.get(status, T.TEXT)
        border = color if status in (StageStatus.CURRENT, StageStatus.BLOCKED) else T.HAIRLINE
        self.setStyleSheet(
            f"#wf_stage_chip {{ background:{T.CARBON_RAISED}; "
            f"border:1px solid {border}; border-radius:{T.RADIUS_MD}px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.SPACE_SM, 6, T.SPACE_SM, 6)
        lay.setSpacing(T.SPACE_SM)

        num = QLabel(str(index + 1))
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setFixedSize(22, 22)
        num.setStyleSheet(
            f"background:{color}; color:{ink}; border-radius:11px; font-weight:bold;")
        lay.addWidget(num)

        text = QLabel(title)
        text.setStyleSheet(
            f"color:{T.TEXT_HI if status is StageStatus.CURRENT else T.TEXT_DIM}; "
            f"font-weight:{'bold' if status is StageStatus.CURRENT else 'normal'};")
        lay.addWidget(text)
        self._status = status


class WorkflowStepper(QWidget):
    """Renders a :class:`WorkflowState`. Emits ``go_to_tab`` with the next-tab key
    when the next-action button is pressed."""

    go_to_tab = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(T.SPACE_SM)

        self._chip_row = QHBoxLayout()
        self._chip_row.setSpacing(T.SPACE_XS)
        chip_host = QWidget()
        chip_host.setLayout(self._chip_row)
        chip_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._root.addWidget(chip_host)

        self._action_bar = QFrame()
        self._action_bar.setObjectName("wf_action_bar")
        bar = QHBoxLayout(self._action_bar)
        bar.setContentsMargins(T.SPACE_MD, T.SPACE_SM, T.SPACE_MD, T.SPACE_SM)
        self._progress_lbl = QLabel("")
        self._progress_lbl.setStyleSheet(f"color:{T.TEXT_DIM};")
        self._next_lbl = QLabel("")
        self._next_lbl.setStyleSheet(f"color:{T.TEXT_HI}; font-weight:bold;")
        self._next_lbl.setWordWrap(True)
        self._next_btn = QPushButton("Go")
        self._next_btn.setMinimumHeight(T.TOUCH_MIN_H)
        self._next_btn.clicked.connect(self._on_next)
        bar.addWidget(self._progress_lbl)
        bar.addSpacing(T.SPACE_MD)
        bar.addWidget(self._next_lbl, 1)
        bar.addWidget(self._next_btn)
        self._root.addWidget(self._action_bar)

        self._next_tab = ""

    def set_state(self, state: WorkflowState) -> None:
        # Clear existing chips.
        while self._chip_row.count():
            item = self._chip_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for stage in state.stages:
            self._chip_row.addWidget(_StageChip(stage.index, stage.title, stage.status))
        self._chip_row.addStretch(1)

        self._progress_lbl.setText(f"{state.done_count} / {state.total} done")
        current = state.stages[state.current_index] if not state.complete else None
        if current is not None and current.blocker:
            self._next_lbl.setText(f"⚠ {current.blocker}  —  {state.next_action}")
            tone = T.WARN
        else:
            self._next_lbl.setText(state.next_action)
            tone = T.NGR_GREEN
        self._action_bar.setStyleSheet(
            f"#wf_action_bar {{ background:{T.CARBON_RAISED}; "
            f"border-left:3px solid {tone}; border-radius:{T.RADIUS_MD}px; }}")
        self._next_tab = state.next_tab or ""
        self._next_btn.setEnabled(bool(self._next_tab) and not state.complete)
        self._next_btn.setText("Done" if state.complete else "Go to next step")

    def _on_next(self) -> None:
        if self._next_tab:
            self.go_to_tab.emit(self._next_tab)
