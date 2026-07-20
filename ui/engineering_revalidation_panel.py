"""Re-validation Status section (Engineering Brain Program 2, Phase 26).

A READ-ONLY section of the Development History page. It shows which established engineering
knowledge remains current/protected and which may need re-validation because context/version
changed or evidence weakened - reported as status only. Dates are evidence data, not an automatic
expiry.

There is NO control that creates, schedules, applies, optimises, tests or mutates anything, and NO
setup values are shown. States use text labels + structure (not colour alone). It renders an
immutable pre-built dict handed to ``update_result`` (the heavy build runs off the Qt thread).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import engineering_revalidation_vm as vm

_PROTECT_TITLES = ("Current / protected knowledge",)
_WARN_TITLES = ("Re-validation required", "Invalidated by version change", "Weakened by conflict",
                "Weakened by regression")


class EngineeringRevalidationPanel(QWidget):
    """Self-contained section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_programme_revalidation_report``. Safe on None / not-ok / empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Knowledge Re-validation Status")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. Which established knowledge remains current/protected and which "
                      "may need re-validation because context or GT7 version changed, or evidence "
                      "weakened (conflict / regression / dependence). Dates are evidence data, not "
                      "an automatic expiry; a version change re-validates only version-sensitive "
                      "knowledge. Nothing is scheduled, tested or applied; no setup values.")
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
        for card in vm.revalidation_cards(data):
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
            protect = section_title in _PROTECT_TITLES
            warn = section_title in _WARN_TITLES
            tag = "[PROTECT] " if protect else ("[REVIEW] " if warn else "")
            hdr = QLabel(tag + section_title)
            weight = "700" if (protect or warn) else "600"
            colour = ngr.SUCCESS if protect else (ngr.WARN if warn else ngr.TEXT_HI)
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
