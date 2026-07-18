"""Structured Setup Builder recommendation view (UAT Finding 3).

Replaces the single ``QTextEdit.setHtml()`` blob with a header + tabbed workflow
(Recommendation table / Why / Practice Analysis / Test Plan / Advanced Evidence)
and a persistent action bar. Renders a ``SetupRecommendationVM``; changed rows
highlight immediately (at generate), and ``mark_applied`` only changes status.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QListWidget, QPushButton, QTextEdit,
    QGroupBox,
)

from ui.setup_recommendation_vm import (
    SetupRecommendationVM, PROPOSED, APPLIED, REJECTED,
)

_HL_ROW = "#25401F"     # highlighted changed-row background
_APPLIED_ROW = "#1E3A2A"
_REJECTED_FG = "#B06060"

RECO_COLS = ("Field", "Current", "Recommended", "Delta", "Status", "Confidence")


class SetupRecommendationView(QWidget):
    apply_in_game = pyqtSignal()
    values_entered = pyqtSignal()
    start_validation = pyqtSignal()
    submit_feedback = pyqtSignal()
    reject_recommendation = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm: Optional[SetupRecommendationVM] = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # -------- Header --------
        self._header_box = QGroupBox("Recommendation")
        hg = QGridLayout(self._header_box)
        hg.setContentsMargins(8, 6, 8, 6)
        hg.setHorizontalSpacing(16)
        self._h_labels: dict[str, QLabel] = {}
        fields = ["Car", "Track", "Layout", "Setup", "Active setup",
                  "Status", "Confidence", "Primary issue"]
        for i, name in enumerate(fields):
            r, c = divmod(i, 4)
            cap = QLabel(f"{name}:")
            cap.setStyleSheet("color:#8A9099; font-size:10px;")
            val = QLabel("—")
            val.setStyleSheet("color:#E0E0E0; font-size:11px; font-weight:bold;")
            val.setWordWrap(True)
            hg.addWidget(cap, r * 2, c)
            hg.addWidget(val, r * 2 + 1, c)
            self._h_labels[name] = val
        root.addWidget(self._header_box)

        # -------- Tabs --------
        self._tabs = QTabWidget()

        # Recommendation table
        self._table = QTableWidget(0, len(RECO_COLS))
        self._table.setHorizontalHeaderLabels(list(RECO_COLS))
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabs.addTab(self._table, "Recommendation")

        # Why
        self._why_list = QListWidget()
        self._tabs.addTab(self._why_list, "Why")

        # Practice Analysis (compact — full surface lives on Practice Review)
        self._practice_lbl = QLabel(
            "Run “Analyse Practice Patterns” on the Practice Review tab to see "
            "cross-lap corner patterns behind this recommendation.")
        self._practice_lbl.setWordWrap(True)
        self._practice_lbl.setStyleSheet("color:#9AA0A6; padding:8px;")
        self._tabs.addTab(self._practice_lbl, "Practice Analysis")

        # Test Plan
        self._test_list = QListWidget()
        self._tabs.addTab(self._test_list, "Test Plan")

        # Advanced Evidence
        self._advanced = QTextEdit()
        self._advanced.setReadOnly(True)
        self._tabs.addTab(self._advanced, "Advanced Evidence")

        root.addWidget(self._tabs)

        # -------- Persistent action bar --------
        bar = QHBoxLayout()
        self._btn_apply = QPushButton("Apply in Game")
        self._btn_values = QPushButton("Values Entered")
        self._btn_validate = QPushButton("Start Validation")
        self._btn_feedback = QPushButton("Submit Feedback")
        self._btn_reject = QPushButton("Reject Recommendation")
        self._btn_apply.clicked.connect(self.apply_in_game)
        self._btn_values.clicked.connect(self.values_entered)
        self._btn_validate.clicked.connect(self.start_validation)
        self._btn_feedback.clicked.connect(self.submit_feedback)
        self._btn_reject.clicked.connect(self.reject_recommendation)
        for b in (self._btn_apply, self._btn_values, self._btn_validate,
                  self._btn_feedback, self._btn_reject):
            bar.addWidget(b)
        bar.addStretch()
        self._next_action_lbl = QLabel("")
        self._next_action_lbl.setStyleSheet("color:#8BC34A; font-size:10px;")
        bar.addWidget(self._next_action_lbl)
        root.addLayout(bar)

        self._set_actions_enabled(False)

    # ------------------------------------------------------------------ #
    def _set_actions_enabled(self, has_reco: bool) -> None:
        self._btn_apply.setEnabled(has_reco)
        self._btn_values.setEnabled(has_reco)
        self._btn_reject.setEnabled(has_reco)
        # Validation/feedback come after applying.

    def set_vm(self, vm: SetupRecommendationVM) -> None:
        self._vm = vm
        h = vm.header
        self._h_labels["Car"].setText(h.car or "—")
        self._h_labels["Track"].setText(h.track or "—")
        self._h_labels["Layout"].setText(h.layout or "—")
        self._h_labels["Setup"].setText(
            f"{h.setup_name} · rev {h.revision}" if h.setup_name else "—")
        self._h_labels["Active setup"].setText(h.active_setup or "none applied")
        self._h_labels["Status"].setText(h.status or "—")
        self._h_labels["Confidence"].setText(h.confidence or "—")
        self._h_labels["Primary issue"].setText(h.primary_issue or "—")

        # Recommendation table.
        rows = vm.field_rows
        self._table.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            cells = [row.setting, row.current_value, row.recommended_value,
                     row.delta, row.status.title(), row.confidence or "—"]
            for ci, val in enumerate(cells):
                item = QTableWidgetItem(str(val))
                if row.status == REJECTED:
                    item.setForeground(_qcolor(_REJECTED_FG))
                elif row.highlighted and row.status == PROPOSED:
                    item.setBackground(_qcolor(_HL_ROW))
                elif row.status == APPLIED:
                    item.setBackground(_qcolor(_APPLIED_ROW))
                self._table.setItem(ri, ci, item)

        # Why cards.
        self._why_list.clear()
        for c in vm.why_cards:
            lines = [f"{c.setting}"]
            if c.symptom:
                lines.append(f"  Symptom: {c.symptom}")
            if c.rationale:
                lines.append(f"  Rationale: {c.rationale}")
            if c.evidence:
                lines.append("  Evidence: " + "; ".join(c.evidence))
            if c.alternatives:
                lines.append("  Alternatives: " + "; ".join(c.alternatives))
            meta = []
            if c.risk:
                meta.append(f"risk {c.risk}")
            if c.confidence:
                meta.append(f"confidence {c.confidence}")
            if c.driver_style_alignment:
                meta.append(f"style {c.driver_style_alignment}")
            if c.rule_source:
                meta.append(f"rule {c.rule_source}")
            if meta:
                lines.append("  (" + ", ".join(meta) + ")")
            self._why_list.addItem("\n".join(lines))

        # Test plan.
        self._test_list.clear()
        for s in vm.test_plan:
            self._test_list.addItem(str(s))

        # Advanced.
        self._advanced.setPlainText("\n".join(vm.advanced_evidence)
                                    if vm.advanced_evidence else "No advanced diagnostics.")

        self._set_actions_enabled(vm.has_recommendation)
        self._update_next_action()

    def mark_applied(self) -> None:
        """Flip proposed rows to applied without changing what is shown."""
        if self._vm is not None:
            self.set_vm(self._vm.mark_applied())

    def current_vm(self) -> Optional[SetupRecommendationVM]:
        return self._vm

    def _update_next_action(self) -> None:
        vm = self._vm
        if vm is None or not vm.has_recommendation:
            self._next_action_lbl.setText("")
            return
        if vm.proposed_rows():
            self._next_action_lbl.setText("Next: apply the proposed changes in game.")
        else:
            self._next_action_lbl.setText("Next: run validation laps, then submit feedback.")


def _qcolor(hex_str: str):
    from PyQt6.QtGui import QColor
    return QColor(hex_str)
