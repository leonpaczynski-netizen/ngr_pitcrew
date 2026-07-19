"""Assurance-Driven Engineering Priority section (Engineering Brain Program 2, Phase 32).

A READ-ONLY section of the Development History page. It ranks the EVIDENCE the engineering programme
should collect next to most efficiently improve programme assurance, derived from the Phase-31
assurance findings. It is advisory only: it is the highest-priority evidence to collect, NOT an
approved experiment, NOT a setup recommendation, and NOT permission to Apply.

There is NO control that creates, schedules, applies, optimises, runs, tests or mutates anything, NO
editable priority input, and NO setup values are shown. States use text labels + structure (not
colour alone). It renders an immutable pre-built dict handed to ``update_result`` (the heavy build
runs off the Qt thread).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import assurance_engineering_priority_vm as vm

_PRIORITY_TITLES = ("Highest-priority evidence to collect",)
_DEFER_TITLES = ("Deferred (blocked by a prerequisite or not currently collectable)",
                 "Unresolved prerequisites")


class AssuranceEngineeringPriorityPanel(QWidget):
    """Self-contained section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_assurance_engineering_priority_report``. Safe on None / not-ok / empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Assurance-Driven Engineering Priority")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only, advisory only. Given the current assurance verdict, the "
                      "highest-priority EVIDENCE to collect next and why - it is not an approved "
                      "experiment, not a setup recommendation, and not permission to Apply. "
                      "Independent evidence outranks dependent repetition; contradictions need "
                      "discriminating evidence; assumptions stay assumptions until established; "
                      "missing evidence is untested, not disproven; expected impact is potential, "
                      "never guaranteed. No dates, sessions or resources are assigned; no setup "
                      "values.")
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
        for card in vm.priority_cards(data):
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
            prio = section_title in _PRIORITY_TITLES
            defer = section_title in _DEFER_TITLES
            tag = "[COLLECT] " if prio else ("[DEFER] " if defer else "")
            hdr = QLabel(tag + section_title)
            weight = "700" if (prio or defer) else "600"
            colour = ngr.WARN if prio else (ngr.TEXT_DIM if defer else ngr.TEXT_HI)
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
