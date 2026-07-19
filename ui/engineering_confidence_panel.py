"""Engineering Knowledge Quality section (Engineering Brain Program 2, Phase 20).

A READ-ONLY section of the Development History page. For each engineering campaign it shows the
confidence-weighted knowledge quality (overall confidence + a fully-explained component
breakdown), the development ROI (expected information / confidence gain, knowledge gap, cost to
close it, remaining risk) and the campaign opportunity (how worthwhile more work is).

There is NO Apply / Approve / Freeze / Complete / Execute / edit control - it measures trust
and remaining engineering return only. Confidence/ROI NEVER complete a campaign (completion
stays governed by Phase 18), and the frozen Apply gate remains the sole route to the car. It
renders an immutable pre-built dict handed to ``update_result`` (the heavy build runs off the
Qt thread).

Named ``EngineeringConfidencePanel`` (not ``EngineeringKnowledgePanel``, which the Phase-12
vehicle-dynamics knowledge panel already owns).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import engineering_confidence_vm as vm


class EngineeringConfidencePanel(QWidget):
    """Self-contained section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_engineering_knowledge_quality``. Safe on None / not-ok / empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Engineering Knowledge Quality - Confidence, ROI & Opportunity")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. For each campaign: how trustworthy its conclusions are "
                      "(confidence with a fully-explained breakdown), how much engineering "
                      "knowledge a further session could add (ROI, cost to close the gap), and "
                      "whether more work is worthwhile. It ranks nothing and completes nothing; "
                      "nothing is applied, frozen or edited here.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(note)

        self._header = QLabel("")
        self._header.setWordWrap(True)
        self._header.setStyleSheet(ngr.banner_qss("info"))
        self._root.addWidget(self._header)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(ngr.SPACE_SM)
        self._root.addWidget(self._cards_container)
        self._cards: list = []

        self.update_result(None)

    def update_result(self, result: Optional[dict]) -> None:
        self._clear_cards()
        data = vm.build(result)
        self._header.setText(vm.header_text(data))
        self._header.setStyleSheet(ngr.banner_qss(vm.banner_tone(data)))
        if vm.is_empty(data):
            return
        for card in vm.quality_cards(data):
            self._add_card(card)

    def _clear_cards(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []

    def _add_card(self, card: dict) -> None:
        box = QGroupBox(f"{card['title']}   -   {card['status']}")
        box.setStyleSheet(ngr.card_qss())
        lay = QVBoxLayout(box)
        for section_title, lines in card["sections"]:
            hdr = QLabel(section_title)
            hdr.setStyleSheet(f"color:{ngr.TEXT_HI}; font-weight:600; "
                              f"font-size:{ngr.FS_LABEL}pt;")
            lay.addWidget(hdr)
            for ln in lines:
                if not str(ln).strip():
                    continue
                lbl = QLabel(str(ln))
                lbl.setWordWrap(True)
                lbl.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
                lay.addWidget(lbl)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color:{ngr.HAIRLINE};")
            lay.addWidget(sep)
        self._cards_layout.addWidget(box)
        self._cards.append(box)
