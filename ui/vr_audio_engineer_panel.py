"""PSVR2 Audio-First Race Engineer panel (Program 2, Phases 63/65).

The visual FALLBACK for the audio-first live experience: an always-visible voice/listening STATUS line,
ONE low-density live-strategy card (headline → confidence → next review + an acknowledgement affordance),
and a recovery card on voice failure / telemetry loss. Detailed candidate tables are NOT here — they
belong in the garage/strategy-review. Read-only; issues no pit/tyre/fuel/setup command; acknowledgement
executes nothing; voice is off by default and gated.

Design (from the /ui-ux-pro-max gate): audio is primary, this surface is the non-VR fallback; one primary
message; high-contrast NGR tones; meaning by tag + text (never colour alone). Dict-driven (renders the
``build_live_audio_strategy_view`` dict); the off-thread refresh + stale guard that feeds it live in the
dashboard.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import vr_audio_engineer_vm as vm


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class VrAudioEngineerPanel(QWidget):
    """Read-only audio-first race-engineer surface. Call :meth:`update_result` with the dict from
    ``build_live_audio_strategy_view``."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("PSVR2 Audio-First Race Engineer")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Audio-First Race Engineer")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("For PSVR2 / no-screen driving: essential information is spoken. This visual surface "
                      "is the fallback for non-VR users. Read-only; issues no pit/tyre/fuel/setup command; "
                      "acknowledgement executes nothing; voice off by default and gated.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(note)

        # always-visible voice / listening status line
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setAccessibleName("Voice status")
        self._status.setStyleSheet(ngr.banner_qss("advisory"))
        self._root.addWidget(self._status)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(ngr.SPACE_XS)
        self._root.addWidget(self._cards_container)
        self._cards: list = []

        self.update_result(None)

    def update_result(self, result: Optional[dict]) -> None:
        self._clear()
        self._status.setText(vm.status_line(result))
        self._status.setStyleSheet(ngr.banner_qss(_banner_tone(vm.status_tone(result))))
        self._status.setAccessibleDescription(vm.status_line(result))
        if vm.is_empty(result):
            return
        sc = vm.strategy_card(result)
        if sc:
            self._add_strategy_card(sc)
        rc = vm.recovery_card(result)
        if rc:
            self._add_lines_card(rc)

    def _clear(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []

    def _frame(self, tone: str, title: str, tag: str = "") -> tuple:
        frame = QFrame()
        frame.setAccessibleName(f"{title} - {tag}".strip(" -"))
        frame.setStyleSheet(f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border(tone)}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_XS, ngr.SPACE_MD, ngr.SPACE_XS)
        lay.setSpacing(1)
        hdr = QWidget(); hrow = QHBoxLayout(hdr); hrow.setContentsMargins(0, 0, 0, 0)
        htitle = QLabel(str(title)); htitle.setStyleSheet(ngr.heading_qss(3))
        hrow.addWidget(htitle); hrow.addStretch(1)
        if tag:
            badge = QLabel(str(tag)); badge.setStyleSheet(ngr.badge_qss(tone))
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter); hrow.addWidget(badge)
        lay.addWidget(hdr)
        return frame, lay

    def _add_strategy_card(self, card: dict) -> None:
        frame, lay = self._frame(card.get("tone") or "info", card.get("title") or "Live Strategy",
                                  card.get("status_tag") or "")
        head = QLabel(str(card.get("headline") or "-")); head.setWordWrap(True)
        head.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_BODY}pt; font-weight:600;")
        lay.addWidget(head)
        meta = QLabel(f"Confidence: {card.get('confidence', '-')}   |   Next review: "
                      f"{card.get('next_review', '-')}")
        meta.setWordWrap(True)
        meta.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        lay.addWidget(meta)
        if card.get("acknowledgeable"):
            ack = QLabel("Acknowledge via PTT — 'acknowledge' (this executes nothing).")
            ack.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(ack)
        self._cards_layout.addWidget(frame)
        self._cards.append(frame)

    def _add_lines_card(self, card: dict) -> None:
        frame, lay = self._frame(card.get("tone") or "warn", card.get("title") or "Recovery", "")
        for ln in card.get("lines", []):
            if not str(ln).strip():
                continue
            lbl = QLabel(str(ln)); lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{ngr.WARN}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(lbl)
        self._cards_layout.addWidget(frame)
        self._cards.append(frame)


def _banner_tone(tone: str) -> str:
    # map a status tone to a banner tone the theme understands
    return {"success": "success", "warn": "warn", "info": "info", "neutral": "advisory"}.get(tone, "advisory")
