"""EngineeringLibrary — progressive-disclosure home for advanced detail (F8).

The driver-facing answer always comes first on the primary surfaces; the deep
engineering evidence lives here: evidence provenance, rule traces, the knowledge
graph, assurance & audit, certification, bench/manual UAT, and development history.
This is the landing that indexes those areas (the existing engineering panels embed
here at cutover). Selecting an area emits ``open_requested(area_key)``.
"""

from __future__ import annotations

from typing import Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QGridLayout, QWidget

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading, Card
from ui.components.buttons import SecondaryActionButton


LIBRARY_AREAS: Tuple[Tuple[str, str, str], ...] = (
    ("development_history", "Development History",
     "Cross-session learning, protected knowledge, experiment history, working-window evolution."),
    ("evidence_provenance", "Evidence & Provenance",
     "Where every conclusion came from — measured vs assumed, per-domain evidence."),
    ("rule_traces", "Rule Traces",
     "The deterministic rule engine's reasoning behind each recommendation."),
    ("knowledge_graph", "Knowledge Graph",
     "Engineering knowledge by domain across compatible events; transfer & confidence."),
    ("readiness_assurance", "Readiness & Assurance",
     "Knowledge readiness, coverage, blind spots, contradictions and audit."),
    ("certification", "Certification",
     "Software-area certification status (physical/live areas stay NOT TESTED)."),
    ("uat", "Bench & Manual UAT",
     "Offline UAT scenarios and the manual evidence ledger."),
    ("season_knowledge", "Season & Knowledge",
     "Season development, campaigns, ROI and knowledge carried forward."),
)


class EngineeringLibrary(QWidget):
    open_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrEngLibrary")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        lay.setSpacing(_t.SPACE_MD)
        lay.addWidget(SectionHeading("ENGINEERING LIBRARY", level=1))
        sub = QLabel("Evidence, rules and advanced detail — the depth behind the driver-facing answers.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        lay.addWidget(sub)

        grid = QGridLayout()
        grid.setHorizontalSpacing(_t.SPACE_MD)
        grid.setVerticalSpacing(_t.SPACE_MD)
        self._buttons: dict[str, SecondaryActionButton] = {}
        for i, (key, title, desc) in enumerate(LIBRARY_AREAS):
            card = Card()
            t = QLabel(title)
            t.setStyleSheet(f"color: {_t.TEXT_HI}; font-weight: 700; font-size: {_t.FS_LABEL}pt;")
            d = QLabel(desc)
            d.setWordWrap(True)
            d.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
            btn = SecondaryActionButton("Open")
            btn.clicked.connect(lambda _=False, k=key: self.open_requested.emit(k))
            self._buttons[key] = btn
            card.add(t)
            card.add(d)
            card.add(btn)
            grid.addWidget(card, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch(1)
