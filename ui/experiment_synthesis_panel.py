"""Bounded Experiment Synthesis panel (Engineering Brain Program 2, Phase 15).

A READ-ONLY, advisory-only panel showing the smallest legal, reversible numeric setup
experiment that tests each eligible Phase-14 hypothesis, off the canonical applied setup
baseline. It shows baseline vs candidate numeric values with provenance, the legal step,
expected response, protected-good behaviours, trade-offs, test protocol, rejection criteria,
reversal, preflight status and ties.

There are NO editable numeric controls and NO Apply / Approve / Revert controls - Phase 15
authors no value and the canonical Apply gate remains the only route to the car. It renders
an immutable pre-built dict handed to ``update_result`` (the heavy build runs off the Qt
thread in the dashboard).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import experiment_synthesis_vm as vm


class ExperimentSynthesisPanel(QWidget):
    """Self-contained panel. Call :meth:`update_result` with the dict from
    ``SessionDB.build_bounded_setup_experiments``. Safe on None / not-ok / empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Minimum-Effective Experiment Synthesis - Candidate Bounded Tests")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Advisory only. The smallest legal, reversible numeric TEST off the "
                      "canonical applied setup - not a final tune, not optimal. Nothing is "
                      "editable or applied here; the canonical Apply gate remains the only "
                      "route to the car.")
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
        for card in vm.result_cards(data):
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
