"""Live UAT Runtime diagnostics panel (Program 2, Phase 69).

A READ-ONLY developer/UAT surface (hosted on the Development History page, NOT the driver Command Centre):
an overall feed/readiness banner + one card per runtime area (feed, session/event binding, race clock,
fuel/pace/tyre-proxy evidence, pit state, strategy readiness, voice/PTT, certification) plus an evidence-gap
and blockers/warnings card. It renders a finished ``LiveUatRuntimeSnapshot`` payload dict — it observes the
production live path and changes nothing. Meaning is carried by a text tag + tone (never colour alone); no
raw object dump is shown.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import uat_runtime_vm as vm


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class UatRuntimePanel(QWidget):
    """Self-contained read-only UAT runtime surface. Call :meth:`update_result` with a
    ``LiveUatRuntimeSnapshot`` payload dict (or its ``.to_dict()``)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("Live UAT Runtime (developer/UAT)")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Live UAT Runtime (developer/UAT)")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only observability of the production live path: feed → canonical race state → "
                      "strategy → voice/PTT → certification. Advisory only — no pit call, setup Apply or "
                      "game control. Automated/bench evidence never certifies physical hardware.")
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
        self._cards_layout.setSpacing(ngr.SPACE_XS)
        self._root.addWidget(self._cards_container)
        self._cards: list = []

        self.update_result(None)

    def update_result(self, result: Optional[dict]) -> None:
        self._clear()
        try:
            self._header.setText(vm.header_text(result))
            self._header.setStyleSheet(ngr.banner_qss(vm.banner_tone(result)))
            self._header.setAccessibleDescription(vm.header_text(result))
            if vm.is_empty(result):
                return
            for card in vm.all_rows(result):
                self._add_card(card)
            self._add_card({"title": "Evidence Gaps", "status_tag": "", "tone": "neutral",
                            "lines": vm.evidence_gaps_lines(result)})
            self._add_card({"title": "Blockers / Warnings", "status_tag": "", "tone": "neutral",
                            "lines": vm.blocker_lines(result)})
        except Exception:  # pragma: no cover - defensive; the page must still render
            pass

    def _clear(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []

    def _add_card(self, card: dict) -> None:
        tone = card.get("tone") or "neutral"
        frame = QFrame()
        frame.setAccessibleName(f"{card['title']} - {card.get('status_tag') or ''}".strip(" -"))
        frame.setStyleSheet(f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border(tone)}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_XS, ngr.SPACE_MD, ngr.SPACE_XS)
        lay.setSpacing(1)
        hdr = QWidget()
        hrow = QHBoxLayout(hdr)
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
        lay.addWidget(hdr)
        for ln in card.get("lines", []):
            if not str(ln).strip():
                continue
            lbl = QLabel(str(ln))
            lbl.setWordWrap(True)
            low = str(ln).lower()
            colour = ngr.WARN if ("[blocker]" in low or "[limitation]" in low) else ngr.TEXT
            lbl.setStyleSheet(f"color:{colour}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(lbl)
        self._cards_layout.addWidget(frame)
        self._cards.append(frame)
