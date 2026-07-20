"""Pre-Flight Engineering Review panel (Engineering Brain Phase 10).

A READ-ONLY panel shown beside the proposed experiment: the experiment, its engineering
rationale, expected consequences, historical outcomes, known risks, protected
behaviours, a constraint summary, confidence, and the engineering checklist + descriptive
risk level. It reviews the exact Phase-5 selection and changes nothing.

There are NO Apply buttons and NO approval controls — Phase 10 reports; authority to
accept or reject stays with Phases 3 / 5 / 6.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QGridLayout, QGroupBox, QHeaderView, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui import ngr_theme as ngr
from ui import preflight_review_vm as vm

_RISK_TONE = {"LOW": "success", "MODERATE": "warn", "HIGH": "danger", "UNKNOWN": "info"}


class PreFlightReviewPanel(QWidget):
    """Self-contained panel. Call :meth:`update_result` with the dict from
    ``SessionDB.build_experiment_preflight``."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        container = QWidget()
        scroll.setWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_MD, ngr.SPACE_MD, ngr.SPACE_MD)
        root.setSpacing(ngr.SPACE_MD)

        title = QLabel("Pre-Flight Engineering Review")
        title.setStyleSheet(ngr.heading_qss(2))
        root.addWidget(title)

        note = QLabel("Read-only review of the proposed experiment. Advisory only — it "
                      "changes nothing and never blocks the recommendation.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        root.addWidget(note)

        self._risk = QLabel("")
        self._risk.setStyleSheet(ngr.banner_qss("info"))
        root.addWidget(self._risk)

        self._exp_grid = QGridLayout()
        root.addWidget(self._boxed("Proposed Experiment", self._exp_grid))

        self._rationale = QLabel("")
        self._rationale.setWordWrap(True)
        self._rationale.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_BODY}pt;")
        rbox = QGroupBox("Engineering Rationale")
        rbox.setStyleSheet(ngr.card_qss())
        rlay = QVBoxLayout(rbox)
        rlay.addWidget(self._rationale)
        root.addWidget(rbox)

        self._checklist = self._table(vm.CHECKLIST_COLUMNS)
        root.addWidget(self._section("Engineering Checklist", self._checklist))

        self._consequences = self._table(vm.CONSEQUENCE_COLUMNS)
        root.addWidget(self._section("Expected Consequences", self._consequences))

        self._risks_tbl = self._table(vm.SECTION_COLUMNS)
        root.addWidget(self._section("Known Risks", self._risks_tbl))

        self._history = self._table(vm.SECTION_COLUMNS)
        root.addWidget(self._section("Historical Outcomes", self._history))

        self._protected = self._table(vm.SECTION_COLUMNS)
        root.addWidget(self._section("Protected Behaviours", self._protected))

        self._constraints = self._table(vm.SECTION_COLUMNS)
        root.addWidget(self._section("Constraint Summary", self._constraints))

        self._empty = QLabel("No proposed experiment to review.")
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet(f"color:{ngr.TEXT_MUTE}; font-size:{ngr.FS_BODY}pt;")
        root.addWidget(self._empty)
        root.addStretch()

    def _table(self, columns) -> QTableWidget:
        t = QTableWidget(0, len(columns))
        t.setHorizontalHeaderLabels(list(columns))
        t.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        return t

    def _section(self, title: str, table: QTableWidget) -> QGroupBox:
        box = QGroupBox(title)
        box.setStyleSheet(ngr.card_qss())
        lay = QVBoxLayout(box)
        lay.addWidget(table)
        return box

    def _boxed(self, title: str, grid: QGridLayout) -> QGroupBox:
        box = QGroupBox(title)
        box.setStyleSheet(ngr.card_qss())
        box.setLayout(grid)
        return box

    def update_result(self, result: Optional[dict]) -> None:
        """Render the pre-flight review. Safe on None / not-ok / empty."""
        result = result if isinstance(result, dict) else {}
        empty = vm.is_empty(result)
        self._empty.setVisible(empty)
        level = vm.risk_level(result)
        self._risk.setText(f"Risk: {level} — {vm.summary_line(result)}")
        self._risk.setStyleSheet(ngr.banner_qss(_RISK_TONE.get(level, "info")))
        self._fill_grid(self._exp_grid, vm.experiment_rows(result))
        self._rationale.setText("\n".join(f"• {l}" for l in vm.rationale_lines(result))
                                or "—")
        self._fill(self._checklist, vm.checklist_rows(result))
        self._fill(self._consequences, vm.consequence_rows(result))
        self._fill(self._risks_tbl, vm.section_rows(result, "regression_risk"))
        self._fill(self._history, (vm.section_rows(result, "historical_success")
                                   + vm.section_rows(result, "historical_failure")))
        self._fill(self._protected, vm.section_rows(result, "protected_impact"))
        self._fill(self._constraints, vm.section_rows(result, "known_constraints"))

    def _fill(self, table: QTableWidget, rows) -> None:
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(str(val)))

    def _fill_grid(self, grid: QGridLayout, rows) -> None:
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for i, (label, value) in enumerate(rows):
            row, col = divmod(i, 2)
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
            val = QLabel(str(value))
            val.setStyleSheet(f"color:{ngr.TEXT_HI}; font-size:{ngr.FS_BODY}pt;")
            grid.addWidget(lbl, row, col * 2)
            grid.addWidget(val, row, col * 2 + 1)
