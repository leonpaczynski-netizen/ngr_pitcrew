"""Engineering Knowledge panel (Engineering Brain Program 2, Phase 12).

A READ-ONLY reference panel that explains the physical mechanism behind each setup element,
grouped by Suspension / Differential / Aero / Tyres / Brakes / Transmission / Weight transfer,
plus load-transfer modes, handling-phase mechanisms and setup interactions. It renders the
deterministic ``strategy.vehicle_dynamics`` knowledge base and changes nothing.

There are NO Apply controls — this authority only explains deterministic engineering
relationships; it never recommends, ranks or authors anything.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QGroupBox, QHeaderView, QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ui import ngr_theme as ngr
from ui import engineering_knowledge_vm as vm


class EngineeringKnowledgePanel(QWidget):
    """Self-contained reference panel. Renders the static knowledge base on construction;
    call :meth:`refresh` to rebuild (the content is deterministic)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        container = QWidget()
        scroll.setWidget(container)
        self._root = QVBoxLayout(container)
        self._root.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_MD, ngr.SPACE_MD, ngr.SPACE_MD)
        self._root.setSpacing(ngr.SPACE_MD)

        title = QLabel("Engineering Knowledge — Why Setup Changes Work")
        title.setStyleSheet(ngr.heading_qss(1))
        self._root.addWidget(title)

        note = QLabel("Deterministic vehicle-dynamics reference. Explains the physical "
                      "mechanism behind each setup element — it recommends nothing and "
                      "changes nothing.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(note)

        self._tables = []
        self.refresh()

    def refresh(self, result: Optional[dict] = None) -> None:
        """(Re)render the knowledge base. Deterministic; safe to call repeatedly."""
        # clear previously built section boxes
        for box in self._tables:
            box.setParent(None)
            box.deleteLater()
        self._tables = []

        data = vm.build(result)
        if vm.is_empty(data):
            lbl = QLabel("Engineering knowledge base is unavailable.")
            lbl.setStyleSheet(f"color:{ngr.TEXT_MUTE}; font-size:{ngr.FS_BODY}pt;")
            self._root.addWidget(lbl)
            self._tables.append(lbl)
            return

        # component groups (spec grouping)
        for key, label in vm.group_titles(data):
            self._add_table(label, vm.COMPONENT_COLUMNS, vm.component_rows(data, key))
        # cross-cutting knowledge
        self._add_table("Load Transfer", vm.LOAD_COLUMNS, vm.load_transfer_rows(data))
        self._add_table("Handling Phases", vm.PHASE_COLUMNS, vm.handling_phase_rows(data))
        self._add_table("Setup Interactions", vm.INTERACTION_COLUMNS,
                        vm.interaction_rows(data))
        self._add_table("Differential (LSD) Model", ("Parameter", "Mechanism"),
                        vm.lsd_rows(data))
        self._add_table("Aerodynamic Model", ("Aspect", "Mechanism"), vm.aero_rows(data))

    def _add_table(self, title: str, columns, rows) -> None:
        box = QGroupBox(title)
        box.setStyleSheet(ngr.card_qss())
        lay = QVBoxLayout(box)
        table = QTableWidget(len(rows), len(columns))
        table.setHorizontalHeaderLabels(list(columns))
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setWordWrap(True)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(str(val)))
        lay.addWidget(table)
        self._root.addWidget(box)
        self._tables.append(box)
