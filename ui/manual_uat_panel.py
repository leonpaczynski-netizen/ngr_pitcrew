"""Manual UAT evidence + release-readiness panel (Program 2, Phase 71).

A developer/UAT surface (hosted on the Development History page) for the user to record REAL physical / live
UAT evidence against one exact release candidate, and to see the honest manual-UAT readiness decision.
Writes are EXPLICIT and user-triggered (the Record button); a unit or bench test can never create a PASS.
Prior evidence is never silently overwritten — a new observation supersedes the prior one and the ledger
preserves both. Read/entry only; it applies no setup, issues no command, and writes no setup history.

Form conventions (post /ui-ux-pro-max): visible labels, a required-field indicator on the status control,
a read-only distinction for the active-observation view, and explicit success feedback on record.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout,
    QWidget,
)

from ui import ngr_theme as ngr
from ui import manual_uat_vm as vm


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class ManualUatPanel(QWidget):
    """Self-contained manual-evidence entry + readiness surface. ``store`` is a ``ManualUatStore`` (record
    target) and ``facts_provider`` supplies the software-gate facts for the readiness recompute. Both may be
    wired later via :meth:`set_context`; without a store the form is read-only."""

    def __init__(self, store=None, facts_provider: Optional[Callable[[], dict]] = None,
                 candidate_commit: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("Manual UAT Evidence (developer/UAT)")
        self._store = store
        self._facts_provider = facts_provider
        self._candidate_commit = str(candidate_commit or "")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Manual UAT Evidence & Release Readiness")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Record REAL physical / live UAT evidence against one exact candidate. Physical "
                      "microphone, wheel/keyboard PTT, TTS, PSVR2 and live GT7 are certified ONLY by your "
                      "evidence — no automated or bench test can create a PASS. Writes are explicit; prior "
                      "evidence is preserved (superseded, never overwritten).")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(note)

        # ---- readiness banner ----
        self._readiness = QLabel("")
        self._readiness.setWordWrap(True)
        self._readiness.setStyleSheet(ngr.banner_qss("advisory"))
        self._root.addWidget(self._readiness)

        # ---- entry form ----
        self._form = self._build_form()
        self._root.addWidget(self._form)

        # ---- active observation + readiness detail cards ----
        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(ngr.SPACE_XS)
        self._root.addWidget(self._cards_container)
        self._cards: list = []

        self._refresh()

    def set_context(self, *, store=None, facts_provider: Optional[Callable[[], dict]] = None,
                    candidate_commit: Optional[str] = None) -> None:
        if store is not None:
            self._store = store
        if facts_provider is not None:
            self._facts_provider = facts_provider
        if candidate_commit is not None:
            self._candidate_commit = str(candidate_commit)
        self._record_btn.setEnabled(self._store is not None)
        self._refresh()

    def _build_form(self) -> QWidget:
        box = QFrame()
        box.setStyleSheet(f"QFrame {{ {ngr.card_qss()} }}")
        grid = QGridLayout(box)
        grid.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_SM, ngr.SPACE_MD, ngr.SPACE_SM)
        grid.setSpacing(ngr.SPACE_SM)

        def _lbl(txt, required=False):
            q = QLabel(txt + (" *" if required else ""))
            q.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
            return q

        self._area_combo = QComboBox()
        for opt in vm.area_options():
            self._area_combo.addItem(f"{opt['label']}  ({opt['category']})", opt["key"])
        self._area_combo.currentIndexChanged.connect(lambda _i: self._refresh_active_only())
        self._status_combo = QComboBox()
        for opt in vm.status_options():
            self._status_combo.addItem(opt["label"], opt["key"])
        self._expected_edit = QLineEdit()
        self._observed_edit = QLineEdit()
        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(48)
        self._defect_edit = QLineEdit()
        self._evidence_edit = QLineEdit()
        self._hardware_edit = QLineEdit()
        for w in (self._expected_edit, self._observed_edit, self._defect_edit, self._evidence_edit,
                  self._hardware_edit):
            w.setStyleSheet(f"QLineEdit {{ background:{ngr.CARBON_HI}; color:{ngr.TEXT}; "
                            f"border:1px solid {ngr.HAIRLINE}; border-radius:{ngr.RADIUS_SM}px; padding:3px 6px; }}")
        self._notes_edit.setStyleSheet(f"QTextEdit {{ background:{ngr.CARBON_HI}; color:{ngr.TEXT}; "
                                       f"border:1px solid {ngr.HAIRLINE}; border-radius:{ngr.RADIUS_SM}px; }}")

        grid.addWidget(_lbl("Certification area", True), 0, 0)
        grid.addWidget(self._area_combo, 0, 1)
        grid.addWidget(_lbl("Result", True), 0, 2)
        grid.addWidget(self._status_combo, 0, 3)
        grid.addWidget(_lbl("Expected behaviour"), 1, 0)
        grid.addWidget(self._expected_edit, 1, 1)
        grid.addWidget(_lbl("Observed behaviour"), 1, 2)
        grid.addWidget(self._observed_edit, 1, 3)
        grid.addWidget(_lbl("Notes"), 2, 0)
        grid.addWidget(self._notes_edit, 2, 1, 1, 3)
        grid.addWidget(_lbl("Defect reference"), 3, 0)
        grid.addWidget(self._defect_edit, 3, 1)
        grid.addWidget(_lbl("Evidence reference"), 3, 2)
        grid.addWidget(self._evidence_edit, 3, 3)
        grid.addWidget(_lbl("Hardware / context"), 4, 0)
        grid.addWidget(self._hardware_edit, 4, 1)

        self._record_btn = QPushButton("Record Observation")
        self._record_btn.setStyleSheet(ngr.primary_button_qss())
        self._record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._record_btn.setMinimumHeight(ngr.TOUCH_MIN_H)
        self._record_btn.setEnabled(self._store is not None)
        self._record_btn.clicked.connect(self._on_record_clicked)
        grid.addWidget(self._record_btn, 4, 3)

        self._feedback = QLabel("")
        self._feedback.setWordWrap(True)
        self._feedback.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        grid.addWidget(self._feedback, 5, 0, 1, 4)
        return box

    # ---- record (explicit user action) ----
    def _on_record_clicked(self) -> None:
        if self._store is None:
            self._feedback.setText("No evidence store wired — cannot record.")
            return
        try:
            from strategy.manual_uat_evidence import make_observation
            area = self._area_combo.currentData()
            status = self._status_combo.currentData()
            obs = make_observation(
                area, status, tested_at="", candidate_commit=self._candidate_commit,
                notes=self._notes_edit.toPlainText(), expected_behaviour=self._expected_edit.text(),
                observed_behaviour=self._observed_edit.text(), defect_reference=self._defect_edit.text(),
                evidence_reference=self._evidence_edit.text(), hardware_context=self._hardware_edit.text())
            ok = self._store.record(obs)
            if ok:
                self._feedback.setText(f"Recorded {str(status).upper()} for '{area}'. Prior evidence "
                                       "preserved. This is your manual evidence — no test created it.")
            else:
                self._feedback.setText("Write failed — evidence not saved. Prior evidence is intact.")
            self._refresh()
        except Exception:  # pragma: no cover - defensive
            self._feedback.setText("Could not record the observation.")

    # ---- readiness / manifest recompute ----
    def _manifest(self) -> dict:
        try:
            from strategy.release_candidate_manifest import build_release_candidate_manifest
            from strategy.manual_uat_evidence import ManualUatLedger
            ledger = self._store.ledger if self._store is not None else ManualUatLedger()
            facts = {}
            if self._facts_provider is not None:
                try:
                    facts = dict(self._facts_provider() or {})
                except Exception:
                    facts = {}
            facts.setdefault("commit", self._candidate_commit)
            return build_release_candidate_manifest(ledger=ledger, **facts).to_dict()
        except Exception:  # pragma: no cover - defensive
            return {}

    def _refresh(self) -> None:
        manifest = self._manifest()
        self._readiness.setText(vm.readiness_header(manifest))
        self._readiness.setStyleSheet(ngr.banner_qss(vm.readiness_tone(manifest)))
        self._readiness.setAccessibleDescription(vm.readiness_header(manifest))
        self._render_cards(manifest)

    def _refresh_active_only(self) -> None:
        self._refresh()

    def _render_cards(self, manifest: dict) -> None:
        self._clear()
        # active observation for the selected area
        area = self._area_combo.currentData() if hasattr(self, "_area_combo") else None
        active = {}
        if self._store is not None and area:
            a = self._store.ledger.active(area)
            active = a.to_dict() if a is not None else {}
        self._add_card({"title": "Active Observation", "tone": vm.status_tone(active.get("status")),
                        "lines": vm.active_observation_lines(active)})
        self._add_card({"title": "Release Candidate", "tone": "neutral",
                        "lines": vm.manifest_tier_lines(manifest)})
        self._add_card({"title": "Manual Progress", "tone": "neutral",
                        "lines": vm.manual_progress_lines(manifest)})
        self._add_card({"title": "Blockers / Caveats", "tone": vm.readiness_tone(manifest),
                        "lines": vm.blocker_lines(manifest)})

    def _clear(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []

    def _add_card(self, card: dict) -> None:
        tone = card.get("tone") or "neutral"
        frame = QFrame()
        frame.setAccessibleName(str(card.get("title") or ""))
        frame.setStyleSheet(f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border(tone)}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_XS, ngr.SPACE_MD, ngr.SPACE_XS)
        lay.setSpacing(1)
        htitle = QLabel(str(card["title"]))
        htitle.setStyleSheet(ngr.heading_qss(3))
        lay.addWidget(htitle)
        for ln in card.get("lines", []):
            if not str(ln).strip():
                continue
            lbl = QLabel(str(ln))
            lbl.setWordWrap(True)
            low = str(ln).lower()
            colour = ngr.WARN if ("[blocker]" in low or "[caveat]" in low) else ngr.TEXT
            lbl.setStyleSheet(f"color:{colour}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(lbl)
        self._cards_layout.addWidget(frame)
        self._cards.append(frame)
