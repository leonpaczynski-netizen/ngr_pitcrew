"""RaceCertificationPanel — the guided race-day certification surface (Live Activation 3 §7-8).

A "follow the bouncing ball" stepper over the certification stages: each stage shows a semantic
state chip (colour + text together, never colour alone), physical stages carry a manual-result
selector (only the user's hardware observation can pass them), a verdict banner leads, and JSON /
Markdown export sits at the foot. The panel RENDERS a report payload — it holds no certification
logic; every state and verdict comes from ``strategy.race_certification`` via the bridge.

Read-only of the domain: the panel emits the user's intent (record a manual result, export) and the
host performs it, then feeds the recomputed report back. Never fabricates a state.
"""
from __future__ import annotations

from typing import Mapping

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import ngr_theme as _t
from ui.components.status import StatusPill

#: certification state → (StatusPill tone, glyph). Colour + glyph + text together.
_STATE_TONE = {
    "pass": ("success", "✓"),
    "conditional": ("warn", "◑"),
    "fail": ("danger", "✕"),
    "blocked": ("danger", "⛔"),
    "in_progress": ("info", "◐"),
    "not_tested": ("neutral", "○"),
}

#: verdict → (label, tone)
_VERDICT_TONE = {
    "certified": ("CERTIFIED", "success"),
    "conditionally_certified": ("CONDITIONALLY CERTIFIED", "warn"),
    "failed": ("FAILED", "danger"),
    "in_progress": ("IN PROGRESS", "info"),
    "not_tested": ("NOT TESTED", "neutral"),
}

_MANUAL_CHOICES = [
    ("— record —", ""),
    ("PASS (observed)", "pass"),
    ("CONDITIONAL", "conditional"),
    ("FAIL", "fail"),
    ("BLOCKED", "blocked"),
    ("Not tested", "not_tested"),
]


def race_certification_vm(payload: Mapping) -> dict:
    """Pure view-model from a report payload (``RaceCertificationReport.as_json_payload()``). Testable
    without Qt: returns the verdict banner + a render row per stage. Never raises."""
    p = payload if isinstance(payload, Mapping) else {}
    verdict = str(p.get("verdict") or "not_tested")
    label, vtone = _VERDICT_TONE.get(verdict, ("NOT TESTED", "neutral"))
    rows = []
    for i, s in enumerate(p.get("stages") or [], 1):
        if not isinstance(s, Mapping):
            continue
        eff = str(s.get("effective_state") or "not_tested")
        tone, glyph = _STATE_TONE.get(eff, ("neutral", "○"))
        note = str(s.get("detail") or s.get("notes") or "")
        if s.get("credited_downgraded"):
            note = (note + "  ⚠ needs manual evidence to pass").strip()
        rows.append({
            "index": i, "key": str(s.get("key") or ""), "title": str(s.get("title") or ""),
            "physical": bool(s.get("physical")), "mandatory": bool(s.get("mandatory")),
            "recorded_state": str(s.get("recorded_state") or "not_tested"),
            "effective_state": eff, "evidence": str(s.get("evidence") or "none"),
            "tone": tone, "glyph": glyph, "note": note,
        })
    return {"verdict": verdict, "verdict_label": label, "verdict_tone": vtone,
            "reason": str(p.get("verdict_reason") or ""), "certified": bool(p.get("certified")),
            "rows": rows}


class RaceCertificationPanel(QFrame):
    #: (stage_key, state, evidence) — the user recorded a manual result for a stage.
    stage_recorded = pyqtSignal(str, str, str)
    #: "json" | "markdown" — the user requested an export.
    export_requested = pyqtSignal(str)
    #: the user asked to (re)build the report from current app state.
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrRaceCert")
        self.setStyleSheet(
            f"#ngrRaceCert {{ background: {_t.ADVISORY_TINT}; "
            f"border: 1px solid {_t.HAIRLINE_SOFT}; "
            f"border-radius: {_t.RADIUS_MD}px; }}")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._suppress = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(_t.SPACE_MD, _t.SPACE_MD, _t.SPACE_MD, _t.SPACE_MD)
        outer.setSpacing(_t.SPACE_SM)

        title = QLabel("RACE-DAY CERTIFICATION")
        title.setStyleSheet(
            f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt; font-weight: 700; "
            f"letter-spacing: 1px;")
        outer.addWidget(title)

        # -- verdict banner --------------------------------------------------- #
        self._verdict = StatusPill("NOT TESTED", "neutral", "○")
        vrow = QHBoxLayout()
        vrow.setSpacing(_t.SPACE_SM)
        vrow.addWidget(self._verdict, 0, Qt.AlignmentFlag.AlignVCenter)
        self._reason = QLabel("")
        self._reason.setWordWrap(True)
        self._reason.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        vrow.addWidget(self._reason, 1)
        outer.addLayout(vrow)

        # -- stage list ------------------------------------------------------- #
        self._stage_host = QVBoxLayout()
        self._stage_host.setSpacing(_t.SPACE_XS)
        outer.addLayout(self._stage_host)
        self._selectors: dict[str, QComboBox] = {}

        # -- export / refresh actions ---------------------------------------- #
        actions = QHBoxLayout()
        actions.setSpacing(_t.SPACE_SM)
        self._btn_refresh = QPushButton("Rebuild from app state")
        self._btn_json = QPushButton("Export JSON")
        self._btn_md = QPushButton("Export Markdown")
        for b in (self._btn_refresh, self._btn_json, self._btn_md):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; border: 1px solid {_t.HAIRLINE_SOFT}; "
                f"border-radius: {_t.RADIUS_SM if hasattr(_t, 'RADIUS_SM') else 6}px; "
                f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt; padding: 4px 10px; }}"
                f"QPushButton:hover {{ color: {_t.TEXT_HI}; }}")
        self._btn_refresh.clicked.connect(lambda: self.refresh_requested.emit())
        self._btn_json.clicked.connect(lambda: self.export_requested.emit("json"))
        self._btn_md.clicked.connect(lambda: self.export_requested.emit("markdown"))
        actions.addWidget(self._btn_refresh)
        actions.addStretch(1)
        actions.addWidget(self._btn_json)
        actions.addWidget(self._btn_md)
        outer.addLayout(actions)

        self._empty = QLabel("No certification started — press Rebuild from app state to begin.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_BODY}pt;")
        outer.addWidget(self._empty)

    # ---------------------------------------------------------------------- #
    def _clear_stages(self) -> None:
        self._selectors.clear()
        while self._stage_host.count():
            item = self._stage_host.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def set_report(self, payload: Mapping) -> None:
        """Render a report payload. Inactive-safe; never raises."""
        try:
            vm = race_certification_vm(payload)
            label, tone = vm["verdict_label"], vm["verdict_tone"]
            glyph = {"success": "✓", "warn": "◑", "danger": "✕", "info": "◐"}.get(tone, "○")
            self._verdict.set_status(label, tone, glyph)
            self._reason.setText(vm["reason"])
            self._clear_stages()
            rows = vm["rows"]
            self._empty.setVisible(not rows)
            self._suppress = True
            for r in rows:
                self._stage_host.addWidget(self._build_stage_row(r))
            self._suppress = False
        except Exception:
            self._suppress = False

    def _build_stage_row(self, r: Mapping) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_t.SPACE_SM)

        num = QLabel(f"{r['index']}.")
        num.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
        num.setFixedWidth(20)
        lay.addWidget(num, 0, Qt.AlignmentFlag.AlignVCenter)

        name = QLabel(r["title"] + (" 🖐" if r["physical"] else ""))
        name.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_CAPTION}pt;")
        name.setToolTip(r["note"])
        lay.addWidget(name, 1, Qt.AlignmentFlag.AlignVCenter)

        chip = StatusPill(r["effective_state"].replace("_", " ").upper(), r["tone"], r["glyph"])
        lay.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)

        # Physical (hardware) stages carry a manual-result selector — only a user observation may
        # pass them. Non-physical stages are credited automatically and show no selector.
        if r["physical"]:
            combo = QComboBox()
            for text, val in _MANUAL_CHOICES:
                combo.addItem(text, val)
            # reflect the recorded state as the current selection
            rec = r["recorded_state"]
            for i in range(combo.count()):
                if combo.itemData(i) == rec:
                    combo.setCurrentIndex(i)
                    break
            combo.setStyleSheet(f"QComboBox {{ font-size: {_t.FS_CAPTION}pt; padding: 2px 6px; }}")
            key = r["key"]
            combo.currentIndexChanged.connect(lambda _i, k=key, c=combo: self._on_record(k, c))
            self._selectors[key] = combo
            lay.addWidget(combo, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _on_record(self, key: str, combo: QComboBox) -> None:
        if self._suppress:
            return
        val = combo.currentData()
        if not val:
            return
        # A user-recorded hardware result is MANUAL evidence — the only evidence that can pass a
        # physical gate.
        self.stage_recorded.emit(str(key), str(val), "manual")
