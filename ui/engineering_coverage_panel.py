"""Evidence Coverage & Blind-Spot section (Engineering Brain Program 2, Phase 27).

A READ-ONLY section of the Development History page. It maps where each known engineering domain's
evidence is well supported and where more evidence would strengthen confidence (a "blind spot"),
reported as coverage status only. A blind spot is NOT a fault and missing coverage means untested,
never wrong.

There is NO control that creates, schedules, applies, optimises, tests or mutates anything, and NO
setup values are shown. States use text labels + structure (not colour alone). It renders an
immutable pre-built dict handed to ``update_result`` (the heavy build runs off the Qt thread).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import engineering_coverage_vm as vm

_GAP_TITLES = ("Blind spots (more evidence would strengthen these)",)
_GOOD_TITLES = ("Well-covered domains",)


class EngineeringCoveragePanel(QWidget):
    """Self-contained section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_programme_evidence_coverage_report``. Safe on None / not-ok / empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Evidence Coverage & Blind Spots")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. Where each known engineering domain's evidence is well supported "
                      "and where more evidence would strengthen confidence (a blind spot). A blind "
                      "spot is NOT a fault and missing coverage means untested, never wrong; a large "
                      "dependent-evidence count is not strong coverage; one track / car / driver / "
                      "compound / format is a single context, not multi-context. Nothing is "
                      "scheduled, tested or applied; no setup values.")
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
        for card in vm.coverage_cards(data):
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
            gap = section_title in _GAP_TITLES
            good = section_title in _GOOD_TITLES
            tag = "[REVIEW] " if gap else ("[COVERED] " if good else "")
            hdr = QLabel(tag + section_title)
            weight = "700" if (gap or good) else "600"
            colour = ngr.WARN if gap else (ngr.SUCCESS if good else ngr.TEXT_HI)
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
