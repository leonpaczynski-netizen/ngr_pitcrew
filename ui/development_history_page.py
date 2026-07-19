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
from ui.experiment_synthesis_panel import ExperimentSynthesisPanel
from ui.engineering_lifecycle_panel import EngineeringLifecyclePanel
from ui.engineering_plan_panel import EngineeringPlanPanel
from ui.engineering_campaign_panel import EngineeringCampaignPanel
from ui.engineering_efficiency_panel import EngineeringEfficiencyPanel
from ui.engineering_confidence_panel import EngineeringConfidencePanel
from ui.engineering_season_panel import EngineeringSeasonPanel


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

        # Phase 15 (Program 2) — minimum-effective bounded experiment synthesis (smallest
        # legal reversible numeric TEST off the applied baseline). Advisory; not applied.
        self._synthesis_panel = ExperimentSynthesisPanel()
        root.addWidget(self._synthesis_panel)

        # Phase 16 (Program 2) — guarded experiment lifecycle & closed-loop status (evidence
        # to calibration). Read-only orchestration connecting existing authorities; not applied.
        self._lifecycle_panel = EngineeringLifecyclePanel()
        root.addWidget(self._lifecycle_panel)

        # Phase 17 (Program 2) — experiment portfolio optimisation & information-gain
        # selection: which experiment next, ranked by engineering value. Advisory; not applied.
        self._plan_panel = EngineeringPlanPanel()
        root.addWidget(self._plan_panel)

        # Phase 18 (Program 2) — engineering campaigns: multi-session development programme
        # grouping the portfolio into bounded objectives. Read-only; advisory; not applied.
        self._campaign_panel = EngineeringCampaignPanel()
        root.addWidget(self._campaign_panel)

        # Phase 19 (Program 2) — engineering efficiency: campaign age (from the persisted
        # registry), evidence saturation and cost of knowledge. Read-only; advisory; saturation
        # never completes a campaign; nothing is applied, frozen or edited here.
        self._efficiency_panel = EngineeringEfficiencyPanel()
        root.addWidget(self._efficiency_panel)

        # Phase 20 (Program 2) — engineering knowledge quality: confidence-weighted evidence,
        # development ROI and campaign opportunity. Read-only; advisory; measures trust and
        # remaining engineering return; ranks/completes/applies nothing.
        self._confidence_panel = EngineeringConfidencePanel()
        root.addWidget(self._confidence_panel)

        # Phase 21 (Program 2) — season development plan & cross-campaign knowledge map: the
        # Engineering Director's whole-programme view (summary + relationships + knowledge map).
        # Read-only; advisory; explains engineering only; schedules/completes/applies nothing.
        self._season_panel = EngineeringSeasonPanel()
        root.addWidget(self._season_panel)

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

    def update_experiment_synthesis(self, synthesis_result) -> None:
        """Render the Phase-15 bounded experiment synthesis (read-only, advisory). Receives
        an immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._synthesis_panel.update_result(synthesis_result)

    def update_engineering_lifecycle(self, lifecycle_result) -> None:
        """Render the Phase-16 closed-loop engineering lifecycle (read-only). Receives an
        immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._lifecycle_panel.update_result(lifecycle_result)

    def update_engineering_plan(self, plan_result) -> None:
        """Render the Phase-17 experiment portfolio / engineering plan (read-only, advisory).
        Receives an immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._plan_panel.update_result(plan_result)

    def update_engineering_campaigns(self, campaign_result) -> None:
        """Render the Phase-18 engineering-campaign programme (read-only, advisory). Receives
        an immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._campaign_panel.update_result(campaign_result)

    def update_engineering_efficiency(self, efficiency_result) -> None:
        """Render the Phase-19 engineering-efficiency advisory (read-only). Receives an
        immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._efficiency_panel.update_result(efficiency_result)

    def update_engineering_knowledge_quality(self, quality_result) -> None:
        """Render the Phase-20 engineering knowledge-quality advisory (read-only). Receives an
        immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._confidence_panel.update_result(quality_result)

    def update_season_engineering_report(self, season_result) -> None:
        """Render the Phase-21 season engineering report (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._season_panel.update_result(season_result)

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
