"""Engineering Knowledge Assurance & Audit section (Engineering Brain Program 2, Phase 31 — FINAL).

A READ-ONLY audit section of the Development History page. It audits the whole knowledge programme
for assurance defects and states whether the engineering knowledge can be ASSURED. A single blocking
finding prevents ASSURED; the grade is rule-based over visible severity counts, not an opaque score.

There is NO control that creates, schedules, applies, optimises, tests or mutates anything, and NO
setup values are shown. States use text labels + structure (not colour alone). It renders an
immutable pre-built dict handed to ``update_result`` (the heavy build runs off the Qt thread).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import engineering_assurance_vm as vm

_BLOCK_TITLES = ("Blocking findings (prevent ASSURED)", "Major findings")


class EngineeringAssurancePanel(QWidget):
    """Self-contained audit section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_programme_assurance_report``. Safe on None / not-ok / empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Engineering Knowledge Assurance & Audit")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only audit. Whether the engineering knowledge can be ASSURED, from the "
                      "findings across re-validation, coverage, readiness, contradictions and "
                      "assumptions. A single blocking finding prevents ASSURED; the grade is "
                      "rule-based over visible severity counts, not an opaque score. Hidden "
                      "assumptions, unresolved conflicts, regressions, missing transfer boundaries, "
                      "non-determinism and data mutation are defects. Nothing is scheduled, tested "
                      "or applied; no setup values.")
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
        for card in vm.assurance_cards(data):
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
            block = section_title in _BLOCK_TITLES
            verdict = section_title.startswith("Assurance verdict")
            tag = "[REVIEW] " if block else ("[VERDICT] " if verdict else "")
            hdr = QLabel(tag + section_title)
            weight = "700" if (block or verdict) else "600"
            colour = ngr.WARN if block else (ngr.TEXT_HI if verdict else ngr.TEXT_HI)
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
