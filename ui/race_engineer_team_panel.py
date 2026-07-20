"""Race-Engineer Team Brief section (Engineering Brain Program 2, Phase 38).

A compact READ-ONLY section of the Development History page that renders the integrated race-engineer
team brief for the current context: exact vs transferable evidence, the current best-known setup,
lineage, latest outcome, protected strengths, working windows, driver progression, coaching
priorities, the coordinated crew plan, confidence, missing evidence and the next best action with its
verification criteria.

It is read-only with respect to knowledge and database state. There is NO Apply control, NO setup
mutation, NO experiment/campaign creation, NO scheduler, NO editable grade or priority, NO AI call and
NO automatic export. The heavy build runs OFF the Qt thread (dashboard worker + stale-result guard);
this panel only renders the finished immutable dict.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import race_engineer_team_vm as vm


class RaceEngineerTeamPanel(QWidget):
    """Self-contained read-only section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_race_engineer_team_brief``."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Race-Engineer Team Brief")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. One coordinated race-engineer plan for the current event - context, "
                      "exact vs transferable evidence, current best-PROVEN setup, working windows, "
                      "driver progression, coaching priorities and the next controlled step. It is "
                      "not a certification, not an experiment, not a setup and not permission to "
                      "Apply; it never claims a final or 'ultimate' setup; no setup values.")
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
        for card in vm.brief_cards(data):
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
            hdr.setStyleSheet(f"color:{ngr.TEXT_HI}; font-weight:600; font-size:{ngr.FS_LABEL}pt;")
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
