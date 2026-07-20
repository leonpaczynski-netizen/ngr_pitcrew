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
from ui.engineering_knowledge_graph_panel import EngineeringKnowledgeGraphPanel
from ui.engineering_transfer_panel import EngineeringTransferPanel
from ui.engineering_playbook_panel import EngineeringPlaybookPanel
from ui.engineering_timeline_panel import EngineeringTimelinePanel
from ui.engineering_revalidation_panel import EngineeringRevalidationPanel
from ui.engineering_coverage_panel import EngineeringCoveragePanel
from ui.engineering_readiness_panel import EngineeringReadinessPanel
from ui.engineering_contradiction_panel import EngineeringContradictionPanel
from ui.engineering_assumption_panel import EngineeringAssumptionPanel
from ui.engineering_assurance_panel import EngineeringAssurancePanel
from ui.assurance_engineering_priority_panel import AssuranceEngineeringPriorityPanel
from ui.assurance_review_pack_panel import AssuranceReviewPackPanel
from ui.race_engineer_team_panel import RaceEngineerTeamPanel
from ui.closed_loop_workflow_panel import ClosedLoopWorkflowPanel
from ui.assisted_runtime_panel import AssistedRuntimePanel
from ui.event_preparation_panel import EventPreparationPanel
from ui.race_weekend_panel import RaceWeekendPanel
from ui.certification_panel import CertificationPanel


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

        # Phase 28 (Program 2) — engineering knowledge readiness EXECUTIVE SUMMARY (top-level):
        # per-domain, is the knowledge ready to rely on, plus a transparent rule-based programme
        # grade. Read-only; advisory; 'ready' never means 'apply this setup'; no setup values.
        self._readiness_panel = EngineeringReadinessPanel()
        root.addWidget(self._readiness_panel)

        # Phase 31 (Program 2, FINAL) — engineering knowledge assurance & audit (top-level): audits
        # the whole knowledge programme for assurance defects and states whether the knowledge can be
        # ASSURED (a single blocking finding prevents ASSURED). Read-only; advisory; rule-based grade
        # over visible counts; no setup values.
        self._assurance_panel = EngineeringAssurancePanel()
        root.addWidget(self._assurance_panel)

        # Phase 32 (Program 2) — assurance-driven engineering priority: given the assurance verdict,
        # the highest-priority EVIDENCE to collect next and why (advisory only; not an experiment,
        # setup or Apply). Read-only; pairs with the Phase-31 assurance verdict above it.
        self._priority_panel = AssuranceEngineeringPriorityPanel()
        root.addWidget(self._priority_panel)

        # Phases 33-35 (Program 2) — Assurance Review Pack: on-demand deterministic export of the
        # Phase 26-32 assurance chain, optional baseline comparison, and an external review package.
        # Read-only; advisory; export writes files only on explicit user action; no setup values.
        self._review_pack_panel = AssuranceReviewPackPanel()
        root.addWidget(self._review_pack_panel)

        # Phases 36-38 (Program 2) — Race-Engineer Team Brief: the coordinated, context-safe
        # activation of the whole Engineering Brain into ONE read-only race-engineer plan for the
        # current event. Read-only; advisory; no Apply, no experiment, no setup values.
        self._race_engineer_team_panel = RaceEngineerTeamPanel()
        root.addWidget(self._race_engineer_team_panel)

        # Phases 39-41 (Program 2) — Closed-Loop Engineering Development: the read-only three-step
        # workflow (Evidence Readiness -> Practice Run Plan -> Outcome Review). Read-only; advisory;
        # no Apply, no experiment/outcome creation, no setup values.
        self._closed_loop_panel = ClosedLoopWorkflowPanel()
        root.addWidget(self._closed_loop_panel)

        # Phases 42-44 (Program 2) — Assisted Runtime pit-wall: material-context readiness, the
        # user-confirmed practice workflow and safely-gated live text advisories. Read-only; advisory;
        # no Apply, no experiment/outcome/session creation, no voice, no setup values.
        self._assisted_runtime_panel = AssistedRuntimePanel()
        root.addWidget(self._assisted_runtime_panel)

        # Phases 48-50 (Program 2) — Event Preparation Cycle spine: groups every Practice session for
        # one upcoming NGR round into one cumulative engineering programme (setup convergence, tyre/fuel/
        # strategy maturation), with a preparation timeline and next-action. Read-only; advisory; no
        # Apply, no session binding, no lock/finalise here; no setup values.
        self._event_preparation_panel = EventPreparationPanel()
        root.addWidget(self._event_preparation_panel)

        # Phase 50 (Program 2) — Immersive Race Weekend: the ceremonial climax built FROM the accumulated
        # preparation (final arrival, briefing, scrutineering, chief-engineer plan, qualifying, race
        # briefing, debrief). Read-only; no automatic pit/tyre/fuel command; voice disabled by default.
        self._race_weekend_panel = RaceWeekendPanel()
        root.addWidget(self._race_weekend_panel)

        # Phase 56 (Program 2) — Operational Certification: a developer/UAT surface reporting the evidence
        # supporting each area of the NGR event journey. Read-only; grants nothing; automated/offscreen/
        # replay evidence never awards visual/live/operational certification. Kept off the driver Home.
        self._certification_panel = CertificationPanel()
        root.addWidget(self._certification_panel)

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

        # Phase 22 (Program 2) — engineering knowledge graph & multi-event roll-up: knowledge by
        # engineering domain, maturity, evidence and gaps, rolled up across compatible events.
        # Read-only; advisory; describes knowledge only; schedules/completes/applies nothing.
        self._knowledge_graph_panel = EngineeringKnowledgeGraphPanel()
        root.addWidget(self._knowledge_graph_panel)

        # Phase 23 (Program 2) — engineering knowledge transfer & cross-car reuse: whether
        # established KNOWLEDGE (not setup values) is likely reusable in other compatible
        # contexts. Read-only; advisory; transfers no setup; imports/applies nothing.
        self._transfer_panel = EngineeringTransferPanel()
        root.addWidget(self._transfer_panel)

        # Phase 24 (Program 2) — cross-programme engineering playbook: the reusable engineering
        # knowledge across the car stable, assembled as an INVESTIGATION playbook (not a setup).
        # Read-only; advisory; generates/copies/applies no setup values.
        self._playbook_panel = EngineeringPlaybookPanel()
        root.addWidget(self._playbook_panel)

        # Phase 25 (Program 2) — engineering knowledge timeline & convergence: how understanding
        # evolved over time, where evidence genuinely converged vs only repeated dependently.
        # Read-only; advisory; dates are data not authority; no setup values.
        self._timeline_panel = EngineeringTimelinePanel()
        root.addWidget(self._timeline_panel)

        # Phase 26 (Program 2) — knowledge decay & re-validation status: which established knowledge
        # remains current/protected and which may need re-validation because context/version changed
        # or evidence weakened. Read-only; advisory; dates are evidence data not an expiry; no setup.
        self._revalidation_panel = EngineeringRevalidationPanel()
        root.addWidget(self._revalidation_panel)

        # Phase 27 (Program 2) — evidence coverage & blind-spot mapping: where each known domain is
        # well supported and where more evidence would strengthen confidence. Read-only; advisory;
        # a blind spot is not a fault; missing coverage means untested not wrong; no setup values.
        self._coverage_panel = EngineeringCoveragePanel()
        root.addWidget(self._coverage_panel)

        # Phase 29 (Program 2) — knowledge contradiction resolution: where the evidence contradicts
        # itself and whether each disagreement is resolved by context, by stronger independent
        # evidence, or is genuinely open. Read-only; advisory; never resolved by majority or
        # recency; a contradiction may stay open; no setup values.
        self._contradiction_panel = EngineeringContradictionPanel()
        root.addWidget(self._contradiction_panel)

        # Phase 30 (Program 2) — engineering assumption register: what the current knowledge relies
        # on but has not established (facts are not listed). Read-only; advisory; an assumption can
        # only cap readiness, never create it; conservative bounds are labelled; no setup values.
        self._assumption_panel = EngineeringAssumptionPanel()
        root.addWidget(self._assumption_panel)

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

    def update_programme_knowledge_report(self, knowledge_result) -> None:
        """Render the Phase-22 programme knowledge graph (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._knowledge_graph_panel.update_result(knowledge_result)

    def update_programme_transfer_report(self, transfer_result) -> None:
        """Render the Phase-23 knowledge-transfer report (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._transfer_panel.update_result(transfer_result)

    def update_programme_engineering_playbook(self, playbook_result) -> None:
        """Render the Phase-24 cross-programme engineering playbook (read-only). Receives an
        immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._playbook_panel.update_result(playbook_result)

    def update_programme_knowledge_timeline(self, timeline_result) -> None:
        """Render the Phase-25 engineering knowledge timeline (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._timeline_panel.update_result(timeline_result)

    def update_programme_revalidation_report(self, revalidation_result) -> None:
        """Render the Phase-26 knowledge decay & re-validation status (read-only). Receives an
        immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._revalidation_panel.update_result(revalidation_result)

    def update_programme_evidence_coverage_report(self, coverage_result) -> None:
        """Render the Phase-27 evidence coverage & blind-spot map (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._coverage_panel.update_result(coverage_result)

    def update_programme_contradiction_report(self, contradiction_result) -> None:
        """Render the Phase-29 knowledge contradiction resolution (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._contradiction_panel.update_result(contradiction_result)

    def update_programme_assumption_register(self, assumption_result) -> None:
        """Render the Phase-30 engineering assumption register (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._assumption_panel.update_result(assumption_result)

    def update_programme_assurance_report(self, assurance_result) -> None:
        """Render the Phase-31 engineering knowledge assurance & audit (read-only). Receives an
        immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._assurance_panel.update_result(assurance_result)

    def update_assurance_engineering_priority_report(self, priority_result) -> None:
        """Render the Phase-32 assurance-driven engineering priority (read-only). Receives an
        immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._priority_panel.update_result(priority_result)

    def update_assurance_review_pack(self, review_result) -> None:
        """Render the Phases 33-35 Assurance Review Pack preview (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._review_pack_panel.update_result(review_result)

    def update_race_engineer_team_brief(self, brief_result) -> None:
        """Render the Phases 36-38 Race-Engineer Team Brief (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._race_engineer_team_panel.update_result(brief_result)

    def update_closed_loop_workflow(self, workflow_result) -> None:
        """Render the Phases 39-41 closed-loop engineering workflow (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._closed_loop_panel.update_result(workflow_result)

    def update_assisted_runtime(self, runtime_result) -> None:
        """Render the Phases 42-44 assisted runtime pit-wall (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._assisted_runtime_panel.update_result(runtime_result)

    def update_event_preparation(self, preparation_result) -> None:
        """Render the Phases 48-50 Event Preparation Cycle spine (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._event_preparation_panel.update_result(preparation_result)

    def update_race_weekend(self, weekend_result) -> None:
        """Render the Phase 50 Immersive Race Weekend surface (read-only). Receives an immutable,
        pre-built dict (the heavy build runs off the Qt thread)."""
        self._race_weekend_panel.update_result(weekend_result)

    def update_certification(self, certification_result) -> None:
        """Render the Phase 56 Operational Certification developer/UAT surface (read-only)."""
        self._certification_panel.update_result(certification_result)

    def update_programme_knowledge_readiness_report(self, readiness_result) -> None:
        """Render the Phase-28 engineering knowledge readiness executive summary (read-only).
        Receives an immutable, pre-built dict (the heavy build runs off the Qt thread)."""
        self._readiness_panel.update_result(readiness_result)

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
