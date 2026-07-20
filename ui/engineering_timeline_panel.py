"""Engineering Knowledge Timeline section (Engineering Brain Program 2, Phase 25).

A READ-ONLY section of the Development History page - the temporal knowledge layer. It shows how
each domain's understanding evolved (historical sequence), the current convergence per domain
(independent vs dependent evidence), confirmed-good preservation, unresolved conflicts,
regressions & retired directions, superseded conclusions and the context/transfer limitations
adjacent to each conclusion.

Dates are evidence data, not authority: a newer observation never automatically overrides an
older stronger finding, and repeated dependent evidence is not a new independent confirmation.
There is NO Apply / Create Experiment / Schedule / Optimise / setup-editor / edit control, and NO
setup values are shown. It renders an immutable pre-built dict handed to ``update_result`` (the
heavy build runs off the Qt thread). Distinct states are marked with text tags, never colour
alone.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import engineering_timeline_vm as vm

# Section titles whose content is a confirmed-good protection — rendered visually distinct.
_PROTECT_TITLES = ("Confirmed-good preservation",)
_WARN_TITLES = ("Unresolved conflicts", "Regressions and retired directions")


class EngineeringTimelinePanel(QWidget):
    """Self-contained section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_programme_knowledge_timeline``. Safe on None / not-ok / empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Engineering Knowledge Timeline & Convergence")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. How engineering understanding evolved across events, where "
                      "evidence genuinely converged through INDEPENDENT repeated evidence, where "
                      "it remains unresolved, and where apparent repetition is only duplicated or "
                      "dependent evidence. Dates are evidence data, not authority - a newer "
                      "observation never automatically overrides an older stronger finding. No "
                      "setup values are shown; nothing is applied, scheduled or optimised.")
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
        for card in vm.timeline_cards(data):
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
            # a leading text tag distinguishes state without relying on colour alone.
            tag = "[PROTECT] " if protect else ("[REVIEW] " if warn else "")
            hdr = QLabel(tag + section_title)
            weight = "700" if (protect or warn) else "600"
            colour = ngr.SUCCESS if protect else (ngr.WARN if warn else ngr.TEXT_HI)
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
