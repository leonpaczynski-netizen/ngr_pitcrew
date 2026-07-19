"""Development History page (Engineering Brain Phase 8).

A READ-ONLY cross-session engineering-development visualisation: an engineering
scorecard banner, a long-term metrics grid, a chronological engineering timeline,
resolved / remaining issues, protected behaviours + protected knowledge, an experiment
history table and the working-window evolution. It renders the pure
``ui.development_history_vm`` rows built from ``SessionDB.build_cross_session_memory``.

There are NO Apply / Save / Revert controls and no setup-authoring here — the page
answers "what have we learned over every previous session?" and changes nothing.
Rendering is defensive: a malformed/empty result shows an empty-state note.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QGridLayout, QGroupBox, QHeaderView, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui import ngr_theme as ngr
from ui import development_history_vm as vm
from ui.engineering_context_panel import EngineeringContextPanel
from ui.postflight_review_panel import PostFlightReviewPanel
from ui.engineering_knowledge_panel import EngineeringKnowledgePanel
from ui.mechanism_annotation_panel import MechanismAnnotationPanel
from ui.intervention_hypothesis_panel import InterventionHypothesisPanel


class DevelopmentHistoryPage(QWidget):
    """Self-contained page. Call :meth:`update_result` with the orchestrator dict from
    ``SessionDB.build_cross_session_memory``."""

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

        title = QLabel("Development History — What We've Learned Across Sessions")
        title.setStyleSheet(ngr.heading_qss(1))
        root.addWidget(title)

        self._context = QLabel("")
        self._context.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_LABEL}pt;")
        root.addWidget(self._context)

        note = QLabel("Read-only engineering memory. Learns only from completed, "
                      "canonical engineering reviews — nothing is changed here.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        root.addWidget(note)

        self._band = QLabel("Building picture…")
        self._band.setStyleSheet(ngr.banner_qss("info"))
        root.addWidget(self._band)

        # Phase 9 — cross-context engineering transfer + regression-risk advisory.
        self._context_panel = EngineeringContextPanel()
        root.addWidget(self._context_panel)

        # Phase 11 — prediction calibration (how accurate our expectations have been).
        self._postflight_panel = PostFlightReviewPanel()
        root.addWidget(self._postflight_panel)

        # Phase 13 (Program 2) — mechanism-annotated diagnosis (why each canonical issue
        # occurs), the bridge from Program-1 "what happened" to Phase-12 "why". Read-only.
        self._mechanism_panel = MechanismAnnotationPanel()
        root.addWidget(self._mechanism_panel)

        # Phase 14 (Program 2) — mechanism-constrained intervention hypotheses (defensible
        # controlled-test directions). Advisory-only; authors no value, applies nothing.
        self._intervention_panel = InterventionHypothesisPanel()
        root.addWidget(self._intervention_panel)

        # Phase 12 (Program 2) — deterministic vehicle-dynamics knowledge (static reference).
        self._knowledge_panel = EngineeringKnowledgePanel()
        root.addWidget(self._knowledge_panel)

        self._scorecard_grid = QGridLayout()
        root.addWidget(self._boxed("Engineering Scorecard", self._scorecard_grid))

        self._metrics_grid = QGridLayout()
        root.addWidget(self._boxed("Long-Term Progress Metrics", self._metrics_grid))

        self._comparison_grid = QGridLayout()
        root.addWidget(self._boxed("Latest vs Previous Session", self._comparison_grid))

        self._timeline = self._table(vm.TIMELINE_COLUMNS)
        root.addWidget(self._section("Engineering Timeline", self._timeline))

        self._remaining = self._table(vm.ISSUE_COLUMNS)
        root.addWidget(self._section("Remaining Issues", self._remaining))

        self._resolved = self._table(vm.ISSUE_COLUMNS)
        root.addWidget(self._section("Resolved Issues", self._resolved))

        self._protected = self._table(("Protected behaviour", "Latest verdict"))
        root.addWidget(self._section("Protected Behaviours", self._protected))

        self._knowledge = self._table(vm.KNOWLEDGE_COLUMNS)
        root.addWidget(self._section("Protected Knowledge (never forget)",
                                     self._knowledge))

        self._experiments = self._table(vm.EXPERIMENT_COLUMNS)
        root.addWidget(self._section("Experiment History", self._experiments))

        self._windows = self._table(vm.WINDOW_COLUMNS)
        root.addWidget(self._section("Working-Window Evolution", self._windows))

        self._empty = QLabel("No completed engineering reviews recorded yet for this "
                             "car / track / discipline.")
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet(f"color:{ngr.TEXT_MUTE}; font-size:{ngr.FS_BODY}pt;")
        root.addWidget(self._empty)
        root.addStretch()

    # -- construction helpers ------------------------------------------------
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

    # -- rendering -----------------------------------------------------------
    def update_result(self, result: Optional[dict]) -> None:
        """Render the orchestrator result. Safe on None / not-ok / empty."""
        result = result if isinstance(result, dict) else {}
        empty = vm.is_empty(result)
        self._empty.setVisible(empty)
        self._context.setText(vm.context_label(result))

        band = (result.get("scorecard") or {}).get("band", "insufficient")
        tone = {"strong": "success", "progressing": "info", "stalled": "warn",
                "regressing": "danger"}.get(str(band), "info")
        self._band.setText(vm.scorecard_band_label(result))
        self._band.setStyleSheet(ngr.banner_qss(tone))

        self._fill_grid(self._scorecard_grid, vm.scorecard_row(result))
        self._fill_grid(self._metrics_grid, vm.metrics_rows(result))
        self._fill_grid(self._comparison_grid, vm.comparison_rows(result))
        self._fill_table(self._timeline, vm.timeline_rows(result))
        self._fill_table(self._remaining, vm.remaining_issue_rows(result))
        self._fill_table(self._resolved, vm.resolved_issue_rows(result))
        self._fill_table(self._protected, vm.protected_behaviour_rows(result))
        self._fill_table(self._knowledge, vm.protected_knowledge_rows(result))
        self._fill_table(self._experiments, vm.experiment_history_rows(result))
        self._fill_table(self._windows, vm.window_evolution_rows(result))

    def update_engineering_context(self, context_result) -> None:
        """Render the Phase-9 cross-context engineering advisory (read-only)."""
        self._context_panel.update_result(context_result)

    def update_prediction_calibration(self, calibration_result) -> None:
        """Render the Phase-11 aggregate prediction calibration (read-only)."""
        self._postflight_panel.update_result(None)
        self._postflight_panel.update_calibration(calibration_result)

    def update_mechanism_annotations(self, annotation_result) -> None:
        """Render the Phase-13 mechanism-annotated diagnoses (read-only). Receives an
        immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._mechanism_panel.update_result(annotation_result)

    def update_intervention_hypotheses(self, hypothesis_result) -> None:
        """Render the Phase-14 mechanism-constrained intervention hypotheses (read-only,
        advisory). Receives an immutable, pre-built dict (build runs off the Qt thread)."""
        self._intervention_panel.update_result(hypothesis_result)

    def _fill_table(self, table: QTableWidget, rows) -> None:
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
