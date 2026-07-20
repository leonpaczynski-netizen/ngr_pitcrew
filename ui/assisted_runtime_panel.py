"""Assisted Runtime pit-wall section (Engineering Brain Program 2, Phases 42-44).

ONE coordinated read-only pit-wall in the Development History page: Run State (assisted workflow),
Live Advisory (safely-gated text prompt), and Evidence Progress. It is deliberately a SINGLE panel -
not several competing live radios.

Read-only w.r.t. knowledge/DB: NO Apply control, NO setup mutation, NO experiment/outcome/session
creation, NO scheduler, NO voice/TTS, NO editable grade/priority, NO AI call. The heavy build runs OFF
the Qt thread (dashboard worker + stale-result guard); this panel only renders the finished dict. Each
card states its status in WORDS (a text tag) plus a tone accent.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from ui import ngr_theme as ngr
from ui import assisted_runtime_vm as vm


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class AssistedRuntimePanel(QWidget):
    """Self-contained read-only pit-wall. Call :meth:`update_result` with the dict from
    ``SessionDB.build_assisted_runtime_report``."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("Assisted Runtime Pit Wall")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Assisted Runtime (Practice & Live Advisory)")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. One coordinated pit-wall: a user-confirmed practice-run workflow and "
                      "safely-gated live TEXT advisories. It applies no setup, creates no experiment, "
                      "records no outcome, binds no session automatically, issues no pit/strategy "
                      "command and speaks no voice; nothing is recorded without your explicit "
                      "confirmation through the existing workflow. No setup values.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(note)

        self._header = QLabel("")
        self._header.setWordWrap(True)
        self._header.setStyleSheet(ngr.banner_qss("advisory"))
        self._root.addWidget(self._header)

        # opt-in voice controls (delegated to dashboard handlers; disabled by default). NO Apply /
        # experiment / outcome / pit / strategy control - voice only.
        self._on_toggle_voice: Optional[Callable[[], None]] = None
        self._on_acknowledge: Optional[Callable[[], None]] = None
        self._on_mute: Optional[Callable[[], None]] = None
        self._on_test_voice: Optional[Callable[[], None]] = None
        vbar = QWidget()
        vrow = QHBoxLayout(vbar)
        vrow.setContentsMargins(0, 0, 0, 0)
        self._voice_btn = QPushButton("Enable Voice")
        self._ack_btn = QPushButton("Acknowledge")
        self._mute_btn = QPushButton("Mute Prompt")
        self._test_btn = QPushButton("Test Voice")
        for b in (self._voice_btn, self._ack_btn, self._mute_btn, self._test_btn):
            vrow.addWidget(b)
        vrow.addStretch(1)
        self._root.addWidget(vbar)
        self._voice_btn.clicked.connect(lambda: self._fire(self._on_toggle_voice))
        self._ack_btn.clicked.connect(lambda: self._fire(self._on_acknowledge))
        self._mute_btn.clicked.connect(lambda: self._fire(self._on_mute))
        self._test_btn.clicked.connect(lambda: self._fire(self._on_test_voice))

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(ngr.SPACE_SM)
        self._root.addWidget(self._cards_container)
        self._cards: list = []

        self.update_result(None)

    def set_voice_handlers(self, *, toggle: Optional[Callable[[], None]] = None,
                           acknowledge: Optional[Callable[[], None]] = None,
                           mute: Optional[Callable[[], None]] = None,
                           test: Optional[Callable[[], None]] = None) -> None:
        self._on_toggle_voice = toggle
        self._on_acknowledge = acknowledge
        self._on_mute = mute
        self._on_test_voice = test

    @staticmethod
    def _fire(handler: Optional[Callable[[], None]]) -> None:
        if callable(handler):
            try:
                handler()
            except Exception:  # pragma: no cover - defensive; never propagate into Qt
                pass

    def update_result(self, result: Optional[dict]) -> None:
        self._clear_cards()
        data = vm.build(result)
        self._header.setText(vm.header_text(data))
        self._header.setStyleSheet(ngr.banner_qss(vm.banner_tone(data)))
        self._header.setAccessibleDescription(vm.header_text(data))
        # reflect voice enabled/disabled on the toggle button label.
        voice = (data or {}).get("voice") or {}
        self._voice_btn.setText("Disable Voice" if voice.get("enabled") else "Enable Voice")
        if vm.is_empty(data):
            return
        for card in vm.runtime_cards(data):
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
            stripped = str(ln).strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                lbl.setStyleSheet(f"color:{ngr.TEXT_HI}; font-weight:600; font-size:{ngr.FS_CAPTION}pt;")
            elif stripped.lower().startswith("blocker:") or stripped.lower().startswith("[stop"):
                lbl.setStyleSheet(f"color:{ngr.WARN}; font-size:{ngr.FS_CAPTION}pt;")
            else:
                lbl.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(lbl)

        self._cards_layout.addWidget(frame)
        self._cards.append(frame)
