"""Immersive Race Weekend panel (Engineering Brain Program 2, Phase 50).

The ceremonial race-weekend surface: a phase banner + cards (final arrival, driver briefing,
scrutineering, chief-engineer plan, qualifying, race briefing, debrief). Read-only and built FROM the
accumulated preparation. NO Apply, no setup mutation, no automatic pit/tyre/fuel command; voice
disabled by default. The heavy build runs OFF the Qt thread; this panel renders the finished dict.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import race_weekend_vm as vm


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class RaceWeekendPanel(QWidget):
    """Self-contained read-only race-weekend surface. Call :meth:`update_result` with the race-weekend
    report dict."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("Immersive Race Weekend")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Race Weekend")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. The official weekend is the climax of weeks of preparation, built from "
                      "the accumulated Practice evidence - never rebuilt from scratch. It issues no "
                      "automatic pit, tyre or fuel command; voice is disabled by default and may not "
                      "bypass the VOICE_ELIGIBLE gate. No setup values.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(note)

        self._header = QLabel("")
        self._header.setWordWrap(True)
        self._header.setStyleSheet(ngr.banner_qss("advisory"))
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
        self._header.setAccessibleDescription(vm.header_text(data))
        if vm.is_empty(data):
            return
        for card in vm.weekend_cards(data):
            self._add_card(card)

    def _clear_cards(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []

    def _add_card(self, card: dict) -> None:
        tone = card.get("tone") or "neutral"
        frame = QFrame()
        frame.setAccessibleName(f"{card['title']} - {card.get('status_tag') or ''}".strip(" -"))
        frame.setStyleSheet(
            f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border(tone)}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_SM, ngr.SPACE_MD, ngr.SPACE_SM)
        lay.setSpacing(ngr.SPACE_XS)

        header = QWidget()
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(0, 0, 0, 0)
        htitle = QLabel(str(card["title"]))
        htitle.setStyleSheet(ngr.heading_qss(3))
        hrow.addWidget(htitle)
        hrow.addStretch(1)
        if card.get("status_tag"):
            badge = QLabel(card["status_tag"])
            badge.setStyleSheet(ngr.badge_qss(tone))
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hrow.addWidget(badge)
        lay.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{ngr.HAIRLINE};")
        lay.addWidget(sep)

        for ln in card.get("lines", []):
            if not str(ln).strip():
                continue
            lbl = QLabel(str(ln))
            lbl.setWordWrap(True)
            low = str(ln).lower()
            if low.startswith("blocker:") or low.startswith("risk:"):
                lbl.setStyleSheet(f"color:{ngr.WARN}; font-size:{ngr.FS_CAPTION}pt;")
            else:
                lbl.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(lbl)

        self._cards_layout.addWidget(frame)
        self._cards.append(frame)
