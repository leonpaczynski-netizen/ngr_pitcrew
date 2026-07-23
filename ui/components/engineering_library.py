"""EngineeringLibrary — progressive-disclosure home for advanced detail (F8).

The driver-facing answer always comes first on the primary surfaces; the deep
engineering evidence lives here: evidence provenance, rule traces, the knowledge
graph, assurance & audit, certification, bench/manual UAT, and development history.
This is the landing that indexes those areas (the existing engineering panels embed
here at cutover). Selecting an area emits ``open_requested(area_key)``.
"""

from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QStackedWidget,
)

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
    #: The driver left a detail panel — the host must take its widget back.
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrEngLibrary")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        index_page = QWidget()
        lay = QVBoxLayout(index_page)
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
        self._stack.addWidget(index_page)

        # Detail page — an engineering panel is hosted HERE, inside the new shell.
        # Opening one used to raise the classic dashboard window; the driver should
        # never be thrown back into the old UI to read evidence.
        detail = QWidget()
        dlay = QVBoxLayout(detail)
        dlay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        dlay.setSpacing(_t.SPACE_SM)
        top = QHBoxLayout()
        self._back = SecondaryActionButton("‹ Back to Library")
        self._back.clicked.connect(self._on_back)
        top.addWidget(self._back)
        self._detail_title = SectionHeading("", level=2)
        top.addWidget(self._detail_title)
        top.addStretch(1)
        dlay.addLayout(top)
        self._detail_host = QVBoxLayout()
        dlay.addLayout(self._detail_host, 1)
        self._detail_note = QLabel("")
        self._detail_note.setWordWrap(True)
        self._detail_note.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        dlay.addWidget(self._detail_note)
        self._stack.addWidget(detail)
        self._hosted = None

    # ---- detail hosting ---------------------------------------------------
    def show_panel(self, widget: Optional[QWidget], title: str = "", note: str = "") -> bool:
        """Host ``widget`` inside the Library. False when there is nothing to host."""
        self.release_panel()
        if widget is None:
            self._detail_title.set_text(title or "")
            self._detail_note.setText(
                note or "This area is not available in this build.")
            self._stack.setCurrentIndex(1)
            return False
        self._hosted = widget
        widget.setParent(None)
        self._detail_host.addWidget(widget)
        widget.setVisible(True)
        self._detail_title.set_text(title or "")
        self._detail_note.setText(note or "")
        self._stack.setCurrentIndex(1)
        return True

    def release_panel(self) -> Optional[QWidget]:
        """Detach the hosted widget (so its owner can take it back) and return it."""
        w = self._hosted
        self._hosted = None
        if w is not None:
            self._detail_host.removeWidget(w)
            w.setParent(None)
        return w

    def showing_detail(self) -> bool:
        return self._stack.currentIndex() == 1

    def show_index(self) -> None:
        self._stack.setCurrentIndex(0)

    def _on_back(self) -> None:
        self.back_requested.emit()
        self.show_index()
