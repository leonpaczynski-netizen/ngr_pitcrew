"""Engineering Context panel (Engineering Brain Phase 9).

A READ-ONLY advisory shown before a setup experiment is proposed: it surfaces what
already happened in similar situations — relevant past sessions, known successful
fixes, known failures, stable working windows, protected behaviours, engineering
constraints and regression risks — each with its match strength and evidence.

There are NO Apply controls and NO decision controls. Phase 9 reports; authority to
accept or reject a change always remains with Phases 3 / 5 / 6.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QGroupBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ui import ngr_theme as ngr
from ui import engineering_context_vm as vm


class EngineeringContextPanel(QWidget):
    """Self-contained panel. Call :meth:`update_result` with the dict from
    ``SessionDB.build_engineering_context``."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(ngr.SPACE_MD)

        title = QLabel("Engineering Context — What Already Happened in Similar Situations")
        title.setStyleSheet(ngr.heading_qss(2))
        root.addWidget(title)

        note = QLabel("Read-only lessons from compatible past contexts. Advisory only — "
                      "it decides nothing and never blocks a change.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        root.addWidget(note)

        self._summary = QLabel("")
        self._summary.setStyleSheet(ngr.banner_qss("info"))
        root.addWidget(self._summary)

        self._matches = self._table(vm.MATCH_COLUMNS)
        root.addWidget(self._section("Relevant Past Contexts", self._matches))

        self._risks = self._table(vm.RISK_COLUMNS)
        root.addWidget(self._section("Regression Risks", self._risks))

        self._constraints = self._table(vm.CONSTRAINT_COLUMNS)
        root.addWidget(self._section("Engineering Constraints", self._constraints))

        self._successes = self._table(vm.FIX_COLUMNS)
        root.addWidget(self._section("Known Successful Fixes", self._successes))

        self._failures = self._table(vm.FIX_COLUMNS)
        root.addWidget(self._section("Known Failures", self._failures))

        self._windows = self._table(vm.WINDOW_COLUMNS)
        root.addWidget(self._section("Stable Working Windows", self._windows))

        self._protected = self._table(vm.PROTECTED_COLUMNS)
        root.addWidget(self._section("Protected Behaviours", self._protected))

        self._empty = QLabel("No comparable engineering history yet for this context.")
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

    def update_result(self, result: Optional[dict]) -> None:
        """Render the orchestrator result. Safe on None / not-ok / empty."""
        result = result if isinstance(result, dict) else {}
        empty = vm.is_empty(result)
        self._empty.setVisible(empty)
        self._summary.setText(vm.summary_line(result))
        tone = "warn" if (result.get("regression_risks")) else "info"
        self._summary.setStyleSheet(ngr.banner_qss(tone))
        self._fill(self._matches, vm.matched_context_rows(result))
        self._fill(self._risks, vm.regression_risk_rows(result))
        self._fill(self._constraints, vm.constraint_rows(result))
        self._fill(self._successes, vm.successful_fix_rows(result))
        self._fill(self._failures, vm.failed_fix_rows(result))
        self._fill(self._windows, vm.stable_window_rows(result))
        self._fill(self._protected, vm.protected_behaviour_rows(result))

    def _fill(self, table: QTableWidget, rows) -> None:
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(str(val)))
