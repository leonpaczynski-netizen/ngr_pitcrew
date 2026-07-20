"""Bench UAT runner panel (Program 2, Phase 70).

A READ-ONLY developer/UAT surface (hosted on the Development History page): an explicit "Run Bench UAT
(offline)" button that runs the deterministic bench harness OFF the Qt thread and renders the aggregate
report — overall readiness, totals, per-category counts and explicit failure details. Clearly labelled
OFFLINE: it starts no telemetry listener, sends no physical input, activates no microphone, and can never
mark a physical certification area as passed. Stale-worker protection consistent with the project pattern;
never blocks the UI thread.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import bench_uat_vm as vm


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class BenchUatPanel(QWidget):
    """Self-contained read-only Bench UAT surface. The heavy run is executed off the Qt thread; the panel
    renders only the finished ``BenchUatReport`` payload dict."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("Bench UAT (offline, developer/UAT)")
        self._worker = None
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Bench UAT (offline)")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Deterministic offline scenarios drive the REAL production live path (canonical state → "
                      "strategy → audio/PTT → certification). No network, keyboard, joystick or microphone "
                      "input is used; no physical hardware is certified. Read-only.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(note)

        ctl = QWidget()
        crow = QHBoxLayout(ctl)
        crow.setContentsMargins(0, 0, 0, 0)
        self._run_btn = QPushButton("Run Bench UAT (offline)")
        self._run_btn.setStyleSheet(ngr.primary_button_qss())
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setMinimumHeight(ngr.TOUCH_MIN_H)
        self._run_btn.clicked.connect(self._on_run_clicked)
        crow.addWidget(self._run_btn)
        crow.addStretch(1)
        self._root.addWidget(ctl)

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

    # ---- run (off the Qt thread) ----
    def _on_run_clicked(self) -> None:
        if self._worker is not None:
            return
        try:
            from ui.mechanism_annotation_worker import MechanismAnnotationWorker
            from strategy.bench_uat_harness import run_bench_uat
            self._run_btn.setEnabled(False)
            self._run_btn.setText("Running…")
            self._header.setText("Running bench UAT offline…")
            self._header.setStyleSheet(ngr.banner_qss("info"))

            def _build():
                return run_bench_uat().to_dict()

            worker = MechanismAnnotationWorker(_build)
            self._worker = worker
            worker.finished_ok.connect(lambda result, w=worker: self._on_ready(result, w))
            worker.failed.connect(lambda _m, w=worker: self._on_ready(None, w))
            worker.start()
        except Exception:  # pragma: no cover - defensive
            self._reset_button()

    def _on_ready(self, result, worker=None) -> None:
        # stale-worker guard: ignore a superseded worker
        if worker is not None and self._worker is not worker:
            return
        self._worker = None
        self._reset_button()
        self.update_result(result)

    def _reset_button(self) -> None:
        self._run_btn.setEnabled(True)
        self._run_btn.setText("Run Bench UAT (offline)")

    # ---- render ----
    def update_result(self, result: Optional[dict]) -> None:
        self._clear()
        try:
            self._header.setText(vm.header_text(result))
            self._header.setStyleSheet(ngr.banner_qss(vm.banner_tone(result)))
            self._header.setAccessibleDescription(vm.header_text(result))
            if vm.is_empty(result):
                return
            summary_lines = [f"{row['label']}: {row['value']}" for row in vm.summary_rows(result)]
            self._add_card({"title": "Summary", "status_tag": "", "tone": "neutral", "lines": summary_lines})
            cat_lines = [f"{c['category']}: {c['pass']} passed, {c['fail']} failed"
                         for c in vm.category_counts(result)]
            self._add_card({"title": "By Category", "status_tag": "", "tone": "neutral", "lines": cat_lines})
            self._add_card({"title": "Failures", "status_tag": "", "tone": "neutral",
                            "lines": vm.failure_lines(result)})
            self._add_card({"title": "Scope", "status_tag": "", "tone": "neutral",
                            "lines": [vm.note_text(result)]})
        except Exception:  # pragma: no cover - defensive
            pass

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
            colour = ngr.WARN if "[fail]" in str(ln).lower() else ngr.TEXT
            lbl.setStyleSheet(f"color:{colour}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(lbl)
        self._cards_layout.addWidget(frame)
        self._cards.append(frame)
