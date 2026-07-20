"""Closed-Loop Engineering workflow section (Engineering Brain Program 2, Phases 39-41).

A compact READ-ONLY three-step workflow in the Development History page: (1) Evidence Readiness,
(2) Practice Run Plan, (3) Outcome Review. It shows the exact context, evidence scope + contamination
warnings, the selected EXISTING candidate, the controlled changes and held-constant variables, run
instructions and metrics, the rollback plan, and - once a completed run is supplied - run validity,
expected-vs-observed, promotion eligibility and the next engineering action.

Read-only w.r.t. knowledge and DB state: NO Apply control, NO setup mutation, NO experiment/outcome
creation, NO scheduler, NO editable grade/priority, NO AI call, NO API-key access. The heavy build runs
OFF the Qt thread (dashboard worker + stale-result guard); this panel only renders the finished dict.
Each card states its status in WORDS (a text tag) as well as a tone accent (colour is never the only
signal).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import closed_loop_workflow_vm as vm

_MONO = "Consolas, 'Cascadia Mono', 'DejaVu Sans Mono', monospace"


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class ClosedLoopWorkflowPanel(QWidget):
    """Self-contained read-only section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_closed_loop_workflow_report``."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("Closed-Loop Engineering Workflow")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Closed-Loop Engineering Development")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. A complete engineering loop for the current event: context-safe "
                      "evidence -> an existing candidate's controlled practice-run plan -> outcome "
                      "review, promotion eligibility and the next action. It creates no experiment, "
                      "applies no setup, promotes nothing automatically, and never calls a setup final "
                      "or ultimate. Recording an outcome or applying a setup stays in the existing "
                      "explicit workflow and the frozen Apply gate. No setup values.")
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
        for card in vm.workflow_cards(data):
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
            lbl.setStyleSheet(self._line_qss(str(ln)))
            lay.addWidget(lbl)

        self._cards_layout.addWidget(frame)
        self._cards.append(frame)

    @staticmethod
    def _line_qss(line: str) -> str:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            return f"color:{ngr.TEXT_HI}; font-weight:600; font-size:{ngr.FS_CAPTION}pt;"
        if "conf " in line and "[" in line:
            return f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt; font-family:{_MONO};"
        low = stripped.lower()
        if low.startswith("advisory") or "not permission" in low or "nothing is written" in low:
            return f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt; font-style:italic;"
        return f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;"
