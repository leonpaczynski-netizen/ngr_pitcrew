"""Knowledge Contradiction Resolution section (Engineering Brain Program 2, Phase 29).

A READ-ONLY section of the Development History page. It shows where the evidence contradicts itself
(a confirming and a regressing conclusion for the same domain) and whether each disagreement is
resolved by context, resolved by stronger independent evidence, or genuinely open. A contradiction
is never resolved by majority or recency, and it is allowed to remain open.

There is NO control that creates, schedules, applies, optimises, tests or mutates anything, and NO
setup values are shown. States use text labels + structure (not colour alone). It renders an
immutable pre-built dict handed to ``update_result`` (the heavy build runs off the Qt thread).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import engineering_contradiction_vm as vm

_OPEN_TITLES = ("Open contradictions (evidence does not tell us which is right)",)
_RESOLVED_TITLES = ("Resolved / explained contradictions",)


class EngineeringContradictionPanel(QWidget):
    """Self-contained section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_programme_contradiction_report``. Safe on None / not-ok / empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Knowledge Contradiction Resolution")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. Where the evidence contradicts itself (a confirming and a "
                      "regressing conclusion for the same domain) and whether each disagreement is "
                      "resolved by context, resolved by stronger independent evidence, or genuinely "
                      "open. A contradiction is NEVER resolved by majority or by recency; dependent "
                      "evidence never defeats independent; a version/context mismatch is surfaced; a "
                      "contradiction may stay open. Nothing is scheduled, tested or applied; no "
                      "setup values.")
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
        for card in vm.contradiction_cards(data):
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
            is_open = section_title in _OPEN_TITLES
            resolved = section_title in _RESOLVED_TITLES
            tag = "[OPEN] " if is_open else ("[RESOLVED] " if resolved else "")
            hdr = QLabel(tag + section_title)
            weight = "700" if (is_open or resolved) else "600"
            colour = ngr.WARN if is_open else (ngr.SUCCESS if resolved else ngr.TEXT_HI)
            hdr.setStyleSheet(f"color:{colour}; font-weight:{weight}; font-size:{ngr.FS_LABEL}pt;")
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
