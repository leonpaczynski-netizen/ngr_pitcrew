"""Engineering Playbook section (Engineering Brain Program 2, Phase 24).

A READ-ONLY section of the Development History page - the cross-programme engineering
INVESTIGATION playbook. It assembles the reusable engineering knowledge across the driver's car
stable: programme-wide engineering themes, confirmed-good behaviours to protect, reusable
knowledge and its transfer level, investigation priorities, knowledge to recollect, context-
specific boundaries, historical failed directions and per-target new-programme briefs.

It is an investigation playbook, NOT a baseline setup. There is NO Apply / Create Experiment /
Schedule / Optimise / setup-field editor / numerical-setup / import / copy-setup / edit control -
it assembles and explains existing knowledge only, generates no setup values, and applies
nothing. Completion stays governed by Phase 18, and the frozen Apply gate remains the sole route
to the car. It renders an immutable pre-built dict handed to ``update_result`` (the heavy build
runs off the Qt thread).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import engineering_playbook_vm as vm

# Section titles whose content is a confirmed-good protection — rendered visually distinct.
_PROTECT_TITLES = ("Confirmed-good behaviours to protect",)


class EngineeringPlaybookPanel(QWidget):
    """Self-contained section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_programme_engineering_playbook``. Safe on None / not-ok / empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Cross-Programme Engineering Playbook")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. The reusable engineering knowledge across your car stable, "
                      "assembled as an INVESTIGATION playbook (not a baseline setup): recurring "
                      "themes, confirmed-good behaviours to protect, what is safely reusable and "
                      "at what transfer level, what to investigate first, what to recollect, and "
                      "the explicit boundaries of the knowledge. No setup values are copied, "
                      "generated or applied; all knowledge requires validation in the target.")
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
        for card in vm.playbook_cards(data):
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
            protect = section_title in _PROTECT_TITLES
            weight = "700" if protect else "600"
            colour = ngr.SUCCESS if protect else ngr.TEXT_HI
            hdr.setStyleSheet(f"color:{colour}; font-weight:{weight}; "
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
