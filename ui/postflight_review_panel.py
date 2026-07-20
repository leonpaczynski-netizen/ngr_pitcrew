"""Post-Flight Review panel (Engineering Brain Phase 11).

A READ-ONLY panel showing how accurate the engineering expectation was: the prediction
vs the observed outcome, confirmed expectations, unexpected behaviour, per-category
engineering accuracy, and lessons observed. It compares deterministic objects and
changes nothing.

There are NO Apply controls — Phase 11 only measures accuracy; it never changes
experiments, outcomes, memory or working windows.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QGridLayout, QGroupBox, QHeaderView, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui import ngr_theme as ngr
from ui import postflight_review_vm as vm

_RISK_TONE = {"low": "success", "moderate": "warn", "high": "danger", "unknown": "info"}


class PostFlightReviewPanel(QWidget):
    """Self-contained panel. Call :meth:`update_result` with a reconciliation-record dict
    (``record_experiment_reconciliation``) and optionally :meth:`update_calibration` with
    the calibration summary (``build_prediction_calibration``)."""

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

        title = QLabel("Post-Flight Engineering Review — Prediction vs Reality")
        title.setStyleSheet(ngr.heading_qss(2))
        root.addWidget(title)

        note = QLabel("Read-only reconciliation of what we predicted against what "
                      "actually happened. It measures accuracy and changes nothing.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        root.addWidget(note)

        self._summary = QLabel("")
        self._summary.setStyleSheet(ngr.banner_qss("info"))
        root.addWidget(self._summary)

        self._pvo_grid = QGridLayout()
        root.addWidget(self._boxed("Prediction vs Observed Outcome", self._pvo_grid))

        self._accuracy = self._table(vm.ACCURACY_COLUMNS)
        root.addWidget(self._section("Engineering Accuracy", self._accuracy))

        self._confirmed = self._table(vm.CONSEQUENCE_COLUMNS)
        root.addWidget(self._section("Confirmed Expectations", self._confirmed))

        self._unexpected = self._table(vm.CONSEQUENCE_COLUMNS)
        root.addWidget(self._section("Unexpected Behaviour", self._unexpected))

        self._checklist = self._table(vm.CHECKLIST_COLUMNS)
        root.addWidget(self._section("Checklist Validation", self._checklist))

        self._lessons = QLabel("")
        self._lessons.setWordWrap(True)
        self._lessons.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_BODY}pt;")
        lbox = QGroupBox("Lessons Observed")
        lbox.setStyleSheet(ngr.card_qss())
        llay = QVBoxLayout(lbox)
        llay.addWidget(self._lessons)
        root.addWidget(lbox)

        self._calibration = self._table(vm.CALIBRATION_COLUMNS)
        root.addWidget(self._section("Prediction Calibration (all reconciliations)",
                                     self._calibration))

        self._empty = QLabel("No completed experiment to reconcile yet.")
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
        """Render one reconciliation record. Safe on None / not-ok / empty."""
        result = result if isinstance(result, dict) else {}
        empty = vm.is_empty(result)
        self._empty.setVisible(empty)
        self._summary.setText(vm.summary_line(result))
        rec = result.get("record") or result
        tone = _RISK_TONE.get(str(rec.get("predicted_risk") or "").lower(), "info")
        self._summary.setStyleSheet(ngr.banner_qss(tone))
        self._fill_grid(self._pvo_grid, vm.prediction_vs_outcome_rows(result))
        self._fill(self._accuracy, vm.accuracy_rows(result))
        self._fill(self._confirmed, vm.confirmed_rows(result))
        self._fill(self._unexpected, vm.unexpected_rows(result))
        self._fill(self._checklist, vm.checklist_rows(result))
        lessons = vm.lessons_rows(result)
        self._lessons.setText("\n".join(f"• {l}" for l in lessons) or "—")

    def update_calibration(self, calibration_result: Optional[dict]) -> None:
        """Render the aggregate calibration summary across all reconciliations."""
        self._fill(self._calibration, vm.calibration_rows(calibration_result or {}))

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
