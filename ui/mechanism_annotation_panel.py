"""Mechanism-Annotated Diagnosis panel (Engineering Brain Program 2, Phase 13).

A READ-ONLY panel that explains the vehicle-dynamics MECHANISMS behind each canonical
Program-1 diagnosis, drawn from the Phase-12 knowledge authority. For every eligible
diagnosis it shows, in separated sections: what the app observed, the most-supported
mechanism, the relevant load-transfer and interactions, the competing mechanisms, the
GT7 limitations, the experiment/prediction relationship, and the evidence that would
distinguish the mechanisms.

There are NO Apply / Save / Revert controls and no setup values — it explains physics and
changes nothing. It renders an immutable, pre-built annotation dict handed to
``update_result`` (the heavy build runs off the Qt thread in the dashboard).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget,
)

from ui import ngr_theme as ngr
from ui import mechanism_annotation_vm as vm


class MechanismAnnotationPanel(QWidget):
    """Self-contained panel. Call :meth:`update_result` with the dict from
    ``SessionDB.build_mechanism_annotations``. Safe on None / not-ok / empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Mechanism-Annotated Diagnosis — Why the Car Behaves This Way")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. Explains the physical mechanisms behind each canonical "
                      "diagnosis using deterministic vehicle-dynamics knowledge. It "
                      "recommends no setup value and changes nothing.")
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
        """(Re)render the annotation report. Deterministic; safe to call repeatedly."""
        self._clear_cards()
        data = vm.build(result)
        self._header.setText(vm.header_text(data))
        self._header.setStyleSheet(ngr.banner_qss(vm.banner_tone(data)))
        if vm.is_empty(data):
            return
        for card in vm.annotation_cards(data):
            self._add_card(card)

    # -- construction helpers ------------------------------------------------
    def _clear_cards(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []

    def _add_card(self, card: dict) -> None:
        box = QGroupBox(f"{card['title']}   ·   {card['status']}")
        box.setStyleSheet(ngr.card_qss())
        lay = QVBoxLayout(box)
        lay.setSpacing(ngr.SPACE_XS if hasattr(ngr, "SPACE_XS") else 4)
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
