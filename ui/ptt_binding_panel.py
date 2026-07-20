"""PTT binding + PSVR2 readiness + live certification panel (Program 2, Phases 67/68).

A garage/settings surface (NOT a driving surface): a PTT binding workflow (select type → press-to-bind →
show → test → clear → restore-default, with conflict + unavailable-device messaging), a PSVR2 audio-first
readiness checklist, and the per-area + overall live/VR certification display. Read-only w.r.t. engineering
state; the only writes are operational PTT/voice config via the safe config authority. Dict-driven; never
raises. Design per the /ui-ux-pro-max gate: labelled steps, one primary action, meaning by tag + text.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ui import ngr_theme as ngr
from ui import live_certification_vm as cvm


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class PttBindingPanel(QWidget):
    """Self-contained binding + readiness + certification surface. Call :meth:`update_state` with a dict
    ``{binding_label, binding_conflict, psvr2, certification}``."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("Push-to-Talk & PSVR2 Setup")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Push-to-Talk & PSVR2 Setup")
        title.setStyleSheet(ngr.heading_qss(2))
        root.addWidget(title)

        note = QLabel("Configure push-to-talk and check PSVR2 audio-first readiness here in the garage. "
                      "Bindings and voice preferences are operational settings only — they never change "
                      "engineering state. The microphone is not listening unless you hold PTT.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        root.addWidget(note)

        # --- binding workflow row ---
        step = QWidget(); srow = QHBoxLayout(step); srow.setContentsMargins(0, 0, 0, 0)
        srow.addWidget(QLabel("Input type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["Keyboard", "Controller", "Wheel button"])
        srow.addWidget(self._type_combo)
        self._bind_btn = QPushButton("Press control to bind")
        self._test_btn = QPushButton("Test")
        self._clear_btn = QPushButton("Clear")
        self._default_btn = QPushButton("Restore default")
        for b in (self._bind_btn, self._test_btn, self._clear_btn, self._default_btn):
            b.setMinimumHeight(32)
            srow.addWidget(b)
        srow.addStretch(1)
        root.addWidget(step)

        self._binding_lbl = QLabel("No control bound.")
        self._binding_lbl.setWordWrap(True)
        self._binding_lbl.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
        root.addWidget(self._binding_lbl)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(ngr.SPACE_XS)
        root.addWidget(self._cards_container)
        self._cards: list = []

        self.update_state(None)

    def update_state(self, state: Optional[dict]) -> None:
        self._clear()
        s = state if isinstance(state, dict) else {}
        label = str(s.get("binding_label") or "No control bound.")
        conflict = str(s.get("binding_conflict") or "")
        self._binding_lbl.setText(label + (f"   ⚠ {conflict}" if conflict else ""))

        psvr2 = s.get("psvr2")
        if isinstance(psvr2, dict):
            self._add_readiness_card(psvr2)
        cert = s.get("certification")
        if isinstance(cert, dict):
            self._add_certification_cards(cert)

    def _clear(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []

    def _frame(self, tone: str, title: str, tag: str = "") -> tuple:
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border(tone)}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_XS, ngr.SPACE_MD, ngr.SPACE_XS)
        hdr = QWidget(); hrow = QHBoxLayout(hdr); hrow.setContentsMargins(0, 0, 0, 0)
        ht = QLabel(str(title)); ht.setStyleSheet(ngr.heading_qss(3))
        hrow.addWidget(ht); hrow.addStretch(1)
        if tag:
            badge = QLabel(str(tag)); badge.setStyleSheet(ngr.badge_qss(tone)); hrow.addWidget(badge)
        lay.addWidget(hdr)
        return frame, lay

    def _add_readiness_card(self, psvr2: dict) -> None:
        ready = bool(psvr2.get("ready"))
        frame, lay = self._frame("success" if ready else "warn", "PSVR2 Readiness",
                                 "READY" if ready else "NOT READY")
        for c in psvr2.get("checks", []):
            ok = bool(c.get("pass"))
            mark = "✓" if ok else ("—" if not c.get("required") else "✗")
            lbl = QLabel(f"{mark}  {c.get('label')}")
            lbl.setStyleSheet(f"color:{ngr.TEXT if ok else ngr.WARN}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(lbl)
        summ = QLabel(str(psvr2.get("summary") or "")); summ.setWordWrap(True)
        summ.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        lay.addWidget(summ)
        self._cards_layout.addWidget(frame)
        self._cards.append(frame)

    def _add_certification_cards(self, cert: dict) -> None:
        overall = cvm.overall_card(cert)
        frame, lay = self._frame(overall.get("tone", "neutral"), overall["title"],
                                 overall.get("status_tag", ""))
        for ln in overall.get("lines", []):
            l = QLabel(str(ln)); l.setWordWrap(True)
            l.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(l)
        self._cards_layout.addWidget(frame)
        self._cards.append(frame)
        # per-area rows (shown separately from overall)
        rows = cvm.area_rows(cert)
        if rows:
            arframe, arlay = self._frame("neutral", "Per-Area Certification", f"{len(rows)} areas")
            for r in rows[:40]:
                line = QLabel(f"{r['name']}: {r['level_tag']}"
                              + (f"  — {r['note']}" if r['note'] else ""))
                line.setWordWrap(True)
                line.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
                arlay.addWidget(line)
            self._cards_layout.addWidget(arframe)
            self._cards.append(arframe)
