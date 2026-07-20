"""Event Preparation Cycle panel (Engineering Brain Program 2, Phase 48-50).

The preparation SPINE surface: a next-action banner, a horizontal preparation timeline (actual
activities/dates), and status cards (cumulative progress, setup convergence, strategy maturity,
readiness). Read-only and advisory — NO Apply control, no setup mutation, no experiment/outcome/session
creation, no lock/finalise button here (those are explicit workflows elsewhere), no AI call. The heavy
build runs OFF the Qt thread (dashboard worker + stale-result guard); this panel renders the finished
dict. Each card/node states its status in WORDS plus a tone accent.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget)

from ui import ngr_theme as ngr
from ui import event_preparation_vm as vm


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class EventPreparationPanel(QWidget):
    """Self-contained read-only preparation spine. Call :meth:`update_result` with the dict from
    ``SessionDB.build_event_preparation_report``."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("Event Preparation Cycle")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Event Preparation Cycle")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. Every Practice session for one upcoming NGR round feeds one cumulative "
                      "engineering programme: base/qualifying/race setup development, tyre and fuel "
                      "modelling, driver coaching, strategy and setup convergence. It applies no setup, "
                      "binds no session, and locks or finalises nothing automatically. No setup values.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(note)

        self._header = QLabel("")
        self._header.setWordWrap(True)
        self._header.setStyleSheet(ngr.banner_qss("advisory"))
        self._root.addWidget(self._header)

        # horizontal timeline strip (scrolls if it overflows; never scrolls the page body)
        self._timeline_scroll = QScrollArea()
        self._timeline_scroll.setWidgetResizable(True)
        self._timeline_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._timeline_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._timeline_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._timeline_scroll.setFixedHeight(78)
        self._timeline_host = QWidget()
        self._timeline_row = QHBoxLayout(self._timeline_host)
        self._timeline_row.setContentsMargins(0, 0, 0, 0)
        self._timeline_row.setSpacing(ngr.SPACE_XS)
        self._timeline_scroll.setWidget(self._timeline_host)
        self._root.addWidget(self._timeline_scroll)
        self._timeline_items: list = []

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(ngr.SPACE_SM)
        self._root.addWidget(self._cards_container)
        self._cards: list = []

        self.update_result(None)

    def update_result(self, result: Optional[dict]) -> None:
        self._clear()
        data = vm.build(result)
        self._header.setText(vm.header_text(data))
        self._header.setStyleSheet(ngr.banner_qss(vm.banner_tone(data)))
        self._header.setAccessibleDescription(vm.header_text(data))
        if vm.is_empty(data):
            return
        for node in vm.timeline_nodes(data):
            self._add_timeline_node(node)
        self._timeline_row.addStretch(1)
        for card in vm.progress_cards(data):
            self._add_card(card)

    def _clear(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []
        for n in self._timeline_items:
            n.setParent(None)
            n.deleteLater()
        self._timeline_items = []
        # drop the trailing stretch, if any
        while self._timeline_row.count():
            item = self._timeline_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _add_timeline_node(self, node: dict) -> None:
        tone = node.get("tone") or "neutral"
        frame = QFrame()
        frame.setAccessibleName(f"{node.get('label')} - {node.get('tag')}")
        frame.setStyleSheet(
            f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border(tone)}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(ngr.SPACE_SM, ngr.SPACE_XS, ngr.SPACE_SM, ngr.SPACE_XS)
        lay.setSpacing(1)
        name = QLabel(str(node.get("label") or "-"))
        name.setStyleSheet(f"color:{ngr.TEXT_HI}; font-weight:600; font-size:{ngr.FS_CAPTION}pt;")
        lay.addWidget(name)
        meta = QLabel(f"{node.get('date') or ''}  {node.get('tag') or ''}".strip())
        meta.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        lay.addWidget(meta)
        self._timeline_row.addWidget(frame)
        self._timeline_items.append(frame)

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
            stripped = str(ln).lower()
            if stripped.startswith("missing:") or "missing" in stripped and "readiness" not in stripped:
                lbl.setStyleSheet(f"color:{ngr.WARN}; font-size:{ngr.FS_CAPTION}pt;")
            else:
                lbl.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(lbl)

        self._cards_layout.addWidget(frame)
        self._cards.append(frame)
